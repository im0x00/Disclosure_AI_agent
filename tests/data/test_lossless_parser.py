from __future__ import annotations

import hashlib
import os
import unicodedata
from pathlib import Path

import pytest

from disclosure_ai.data import CorpusCatalog, SourceFormat, describe, parse_artifact
from disclosure_ai.data.tokenizer import tokenize

CORPUS = Path(__file__).resolve().parents[2] / "corpus"


def test_malformed_dart_markup_is_a_byte_exact_partition() -> None:
    source = (
        b'<?xml version="1.0"?><DOCUMENT><P A="1" B=two>'
        b"R&amp;D & raw <" + "현금흐름위험회피".encode() + b">"
        b"</P></DOCUMENT>"
    )
    tokens = tokenize(source, SourceFormat.DART_MARKUP)
    assert b"".join(source[token.start_byte : token.end_byte] for token in tokens) == source
    assert [attribute.name for token in tokens for attribute in token.attributes] == ["A", "B"]
    assert b"<\xed\x98\x84\xea\xb8\x88" in next(
        token.raw(source)
        for token in tokens
        if token.kind.value == "text" and b"raw" in token.raw(source)
    )


@pytest.mark.parametrize(
    ("group", "receipt", "expected_format"),
    [
        ("periodic", "20250515002501", SourceFormat.DART_MARKUP),
        ("major", "20230420000185", SourceFormat.DART_MARKUP),
        ("exchange", "20250325800001", SourceFormat.HTML),
        ("holding", "20240105000218", SourceFormat.DART_MARKUP),
    ],
)
def test_real_group_samples_round_trip(
    group: str, receipt: str, expected_format: SourceFormat
) -> None:
    document = CorpusCatalog(CORPUS).read_document(group, receipt)
    assert document.artifacts
    parsed = parse_artifact(document.artifacts[0])
    assert parsed.source.envelope.detected_format is expected_format
    assert parsed.reconstruct() == parsed.source.content
    assert hashlib.sha256(parsed.reconstruct()).hexdigest() == parsed.source.envelope.sha256


def test_annual_report_keeps_each_file_and_attachment_role() -> None:
    document = CorpusCatalog(CORPUS).read_document("periodic", "20240318000916")
    assert document.metadata["n_files"] == 3
    assert {artifact.envelope.file_name for artifact in document.artifacts} == {
        "20240318000916.xml",
        "20240318000916_00760.xml",
        "20240318000916_00761.xml",
    }
    assert {artifact.envelope.file_role for artifact in document.artifacts} == {
        "primary",
        "attachment",
    }
    assert {artifact.envelope.attachment_code for artifact in document.artifacts} == {
        None,
        "00760",
        "00761",
    }


def test_filesystem_path_bytes_and_nfc_join_key_are_both_kept() -> None:
    document = CorpusCatalog(CORPUS).read_document("holding", "20240105000218")
    envelope = document.artifacts[0].envelope
    assert envelope.corp_folder is not None
    assert envelope.corp_folder_nfc == "현대제철"
    assert unicodedata.is_normalized("NFD", envelope.corp_folder)
    assert os.fsdecode(envelope.relative_path_bytes) == envelope.relative_path
    assert os.fsencode(envelope.file_name) == envelope.file_name_bytes


def test_descriptors_keep_evidence_bytes_and_offsets() -> None:
    catalog = CorpusCatalog(CORPUS)
    periodic_source = catalog.read_document("periodic", "20250515002501").artifacts[0]
    exchange_source = catalog.read_document("exchange", "20250325800001").artifacts[0]
    periodic = describe(parse_artifact(periodic_source))
    exchange = describe(parse_artifact(exchange_source))
    assert periodic.adapter == "periodic"
    assert periodic.document_name is not None
    assert periodic.document_name.raw == "분기보고서".encode()
    assert periodic.document_code is not None and periodic.document_code.text == "11013"
    assert exchange.adapter == "exchange"
    assert exchange.html_title is not None
    assert "투자판단 관련 주요경영사항" in exchange.html_title.text

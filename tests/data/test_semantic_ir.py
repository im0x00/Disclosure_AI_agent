from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import pytest

from disclosure_ai.data import CorpusCatalog, build_semantic_ir, parse_artifact
from disclosure_ai.data.derive import DERIVED_LAYOUT, derive_corpus, derived_path

CORPUS = Path(__file__).resolve().parents[2] / "corpus"


@pytest.mark.parametrize(
    ("group", "receipt"),
    [
        ("periodic", "20250515002501"),
        ("major", "20230420000185"),
        ("exchange", "20250325800001"),
        ("holding", "20240105000218"),
    ],
)
def test_semantic_ir_maps_all_meaningful_text_and_keeps_evidence(group: str, receipt: str) -> None:
    document = CorpusCatalog(CORPUS).read_document(group, receipt)
    artifact = next(item for item in document.artifacts if item.envelope.file_role == "primary")
    ir = build_semantic_ir(parse_artifact(artifact), document.metadata)

    assert ir["schema_version"] == "semantic-structural-ir/v1"
    assert ir["source"]["sha256"] == artifact.envelope.sha256
    assert ir["source"]["relative_path"] == artifact.envelope.relative_path
    assert ir["document_metadata"]["rcept_no"] == receipt
    assert ir["diagnostics"]["lossless_source_verified"] is True
    assert ir["diagnostics"]["all_non_whitespace_text_mapped"] is True
    assert ir["blocks"]

    for evidence in _evidence_objects(ir):
        assert 0 <= evidence["start_byte"] <= evidence["end_byte"] <= len(artifact.content)


def test_exchange_table_becomes_human_readable_label_value_rows() -> None:
    document = CorpusCatalog(CORPUS).read_document("exchange", "20250325800001")
    artifact = document.artifacts[0]
    ir = build_semantic_ir(parse_artifact(artifact), document.metadata)

    assert ir["sections"][0]["title"].startswith("현대제철/")
    table = next(block for block in ir["blocks"] if block["kind"] == "table")
    first_row = table["rows"][0]
    assert first_row["cells"][0]["text"] == "1. 제목"
    assert first_row["cells"][1]["role"] == "value"
    assert first_row["cells"][1]["text"] == "美 전기로 제철소 건설 추진"
    assert first_row["cells"][1]["context_labels"] == ["1. 제목"]


def test_dart_semantic_keys_and_machine_values_are_exposed() -> None:
    document = CorpusCatalog(CORPUS).read_document("holding", "20240105000218")
    artifact = document.artifacts[0]
    ir = build_semantic_ir(parse_artifact(artifact), document.metadata)
    fields = {field["key"]: field for field in ir["semantic_fields"] if field["key"]}

    assert fields["RPT_RSP_DT"]["machine_value"] == "20231228"
    assert fields["RPT_RSP_NM"]["text"] == "기아(주)"
    assert fields["CRP_NM"]["text"] == "현대제철"


def test_derived_writer_mirrors_raw_path_and_resumes(tmp_path: Path) -> None:
    output = tmp_path / DERIVED_LAYOUT
    first = derive_corpus(
        CORPUS,
        output_root=output,
        receipts={"20250325800001"},
        compressed=True,
        progress_every=0,
    )
    assert first.artifacts_written == 1
    assert first.artifacts_skipped == 0

    source_path = "raw/exchange/현대제철/20250325800001/20250325800001.xml"
    target = derived_path(output, source_path, compressed=True)
    assert target.is_file()
    with gzip.open(target, "rt", encoding="utf-8") as stream:
        value = json.load(stream)
    assert value["source"]["relative_path"] == source_path
    assert (output / "manifest.jsonl").is_file()
    assert not (output / "_SUCCESS.json").exists()
    assert json.loads((output / "_RUN.json").read_text(encoding="utf-8"))["complete"] is False

    second = derive_corpus(
        CORPUS,
        output_root=output,
        receipts={"20250325800001"},
        compressed=True,
        progress_every=0,
    )
    assert second.artifacts_written == 0
    assert second.artifacts_skipped == 1


def _evidence_objects(value: Any) -> list[dict[str, int]]:
    found: list[dict[str, int]] = []
    if isinstance(value, dict):
        if set(value) == {"start_byte", "end_byte"}:
            found.append(value)
        for child in value.values():
            found.extend(_evidence_objects(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_evidence_objects(child))
    return found

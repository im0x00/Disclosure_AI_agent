from __future__ import annotations

import gzip
import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any, cast

import pytest

from disclosure_ai.data.semantic_ir import SCHEMA_VERSION
from disclosure_ai.db.derived_reader import (
    IncompleteDerivedError,
    iter_verified_entries,
    read_verified_ir,
)
from disclosure_ai.db.loader import load_structured
from disclosure_ai.db.structured import read_companies, read_documents

CORPUS = Path(__file__).resolve().parents[2] / "corpus"
MIGRATION = Path(__file__).resolve().parents[2] / "src/disclosure_ai/db/migrations/0001_initial.sql"


def test_existing_structured_sources_have_normalized_join_keys() -> None:
    companies = list(read_companies(CORPUS))
    documents = list(read_documents(CORPUS))

    assert len(companies) == 70
    assert len(documents) == 4204
    assert all(unicodedata.is_normalized("NFC", company["corp_name_nfc"]) for company in companies)
    assert all(unicodedata.is_normalized("NFD", company["corp_name_nfd"]) for company in companies)
    assert {document["corp_code"] for document in documents} <= {
        company["corp_code"] for company in companies
    }
    null_subtypes = [document for document in documents if document["doc_subtype"] is None]
    assert len(null_subtypes) == 598
    assert {document["doc_group"] for document in null_subtypes} == {"major"}


def test_structured_load_is_idempotent_upsert_shape() -> None:
    connection = _FakeConnection()
    summary = load_structured(cast(Any, connection), CORPUS)

    assert summary.companies == 70
    assert summary.documents == 4204
    assert [len(batch) for _, batch in connection.cursor_instance.batches] == [70, 140, 4204]
    assert all("ON CONFLICT" in statement for statement, _ in connection.cursor_instance.batches)


def test_migration_defines_unicode_and_queryable_ir_tables() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for required in (
        "corp_name_nfc",
        "corp_name_nfd",
        "source_path_bytes bytea",
        "CREATE TABLE IF NOT EXISTS disclosure.semantic_section",
        "CREATE TABLE IF NOT EXISTS disclosure.semantic_field",
        "CREATE TABLE IF NOT EXISTS disclosure.semantic_cell",
        "CREATE OR REPLACE VIEW disclosure.company_artifact_join",
    ):
        assert required in sql
    assert "doc_subtype text," in sql
    assert "doc_subtype text NOT NULL" not in sql
    assert "semantic_cell (semantic_key, machine_value)" not in sql
    assert "semantic_field (semantic_key, machine_value)" not in sql
    assert "semantic_cell (md5(display_text_nfc))" in sql
    assert "semantic_field (semantic_key, md5(machine_value))" in sql
    assert "semantic_block (text_value_nfc)" not in sql
    assert "context_labels_nfc_gin" not in sql


def test_derived_reader_refuses_in_progress_tree(tmp_path: Path) -> None:
    root = tmp_path / "derived" / "semantic-structural-ir-v1"
    root.mkdir(parents=True)
    with pytest.raises(IncompleteDerivedError):
        list(iter_verified_entries(tmp_path))


def test_derived_reader_requires_hash_and_coverage(tmp_path: Path) -> None:
    root = tmp_path / "derived" / "semantic-structural-ir-v1"
    target = root / "exchange/company/receipt/file.xml.semantic.json.gz"
    target.parent.mkdir(parents=True)
    ir: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source": {"relative_path": "raw/exchange/company/receipt/file.xml", "sha256": "ab" * 32},
        "diagnostics": {
            "lossless_source_verified": True,
            "all_non_whitespace_text_mapped": True,
        },
    }
    with gzip.GzipFile(filename="", mode="wb", fileobj=target.open("wb"), mtime=0) as stream:
        stream.write(json.dumps(ir).encode())
    derived_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    index = {
        "source_path": ir["source"]["relative_path"],
        "source_sha256": ir["source"]["sha256"],
        "derived_path": str(target.relative_to(root)),
        "derived_byte_size": target.stat().st_size,
        "derived_sha256": derived_hash,
    }
    (root / "manifest.jsonl").write_text(json.dumps(index) + "\n", encoding="utf-8")
    (root / "_SUCCESS.json").write_text(
        json.dumps({"complete": True, "schema_version": SCHEMA_VERSION}),
        encoding="utf-8",
    )

    entries = list(iter_verified_entries(tmp_path))
    assert len(entries) == 1
    assert read_verified_ir(*entries[0]) == ir

    target.write_bytes(target.read_bytes() + b"corruption")
    with pytest.raises(ValueError, match="size mismatch"):
        list(iter_verified_entries(tmp_path))


class _FakeCursor:
    def __init__(self) -> None:
        self.batches: list[tuple[str, list[dict[str, Any]]]] = []

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def executemany(self, statement: str, values: list[dict[str, Any]]) -> None:
        self.batches.append((statement, values))


class _FakeTransaction:
    def __enter__(self) -> _FakeTransaction:
        return self

    def __exit__(self, *_: Any) -> None:
        return None


class _FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = _FakeCursor()

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction()

    def cursor(self) -> _FakeCursor:
        return self.cursor_instance

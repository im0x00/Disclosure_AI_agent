from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence.document_relation import DocumentRelation, RelationPredicate
from evidence.document_relation_loader import (
    _relation_rows,
    read_relations,
    replace_document_relations,
    validate_unresolved_for_load,
)
from evidence.loader import read_sql

GRAIN_A = "a" * 64
GRAIN_B = "b" * 64


def relation() -> DocumentRelation:
    return DocumentRelation(
        source_doc_id="exchange_20240102000001",
        source_grain_ids=(GRAIN_A,),
        predicate=RelationPredicate.REVISES,
        target_doc_id="exchange_20240101000001",
        target_grain_ids=(GRAIN_B,),
    )


def test_relation_sql_uses_document_ids_and_optional_grain_arrays() -> None:
    statement = read_sql("011_create_document_relation.sql")

    assert "source_doc_id text NOT NULL" in statement
    assert "relation_id text PRIMARY KEY" in statement
    assert "source_grain_ids text[] NOT NULL" in statement
    assert "target_doc_id text NOT NULL" in statement
    assert "target_grain_ids text[] NOT NULL" in statement
    assert "'revises', 'references', 'terminates'" in statement


def test_read_relations_validates_jsonl_and_rejects_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "relations.jsonl"
    value = relation().model_dump(mode="json")
    path.write_text(
        json.dumps(value) + "\n" + json.dumps(value) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate edges"):
        read_relations(path)


def test_relation_rows_preserve_ordered_grain_ids() -> None:
    rows = tuple(_relation_rows((relation(),)))

    assert rows == (
        {
            "relation_id": "7add1bb37182ff9232a2817d31ede7b9bff4daaddc923b34aca14bcf8fef3cc9",
            "source_doc_id": "exchange_20240102000001",
            "source_grain_ids": [GRAIN_A],
            "predicate": "revises",
            "target_doc_id": "exchange_20240101000001",
            "target_grain_ids": [GRAIN_B],
        },
    )


def test_unresolved_load_gate_allows_reviewed_absence(tmp_path: Path) -> None:
    path = tmp_path / "unresolved.jsonl"
    path.write_text(
        '{"reason":"no_in_corpus_candidate"}\n{"reason":"reviewed_no_match"}\n',
        encoding="utf-8",
    )

    assert validate_unresolved_for_load(path) == {
        "no_in_corpus_candidate": 1,
        "reviewed_no_match": 1,
    }


def test_unresolved_load_gate_rejects_unreviewed_ambiguity(tmp_path: Path) -> None:
    path = tmp_path / "unresolved.jsonl"
    path.write_text('{"reason":"ambiguous_candidates"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="ambiguous_candidates"):
        validate_unresolved_for_load(path)


class FakeCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.inserted: list[dict[str, object]] = []
        self._fetch: list[tuple[object, ...]] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, statement: str) -> None:
        self.executed.append(statement)
        if statement.startswith("SELECT count"):
            self._fetch = [(len(self.inserted),)]
        else:
            self._fetch = []

    def executemany(
        self,
        statement: str,
        rows: list[dict[str, object]],
    ) -> None:
        self.executed.append(statement)
        self.inserted.extend(rows)

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._fetch

    def fetchone(self) -> tuple[object, ...] | None:
        return self._fetch[0] if self._fetch else None


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_value = FakeCursor()
        self.executed: list[str] = []

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, statement: str) -> None:
        self.executed.append(statement)

    def cursor(self) -> FakeCursor:
        return self.cursor_value


def test_replace_document_relations_loads_one_atomic_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    monkeypatch.setattr(
        "evidence.document_relation_loader.psycopg.connect",
        lambda _: connection,
    )

    loaded = replace_document_relations("postgresql://unused", (relation(),))

    assert loaded == 1
    assert connection.cursor_value.inserted[0]["predicate"] == "revises"
    assert connection.cursor_value.executed[0] == "DELETE FROM corpus.document_relation"
    assert any(
        "relation grain endpoints do not match" not in statement
        and "CROSS JOIN LATERAL" in statement
        for statement in connection.cursor_value.executed
    )

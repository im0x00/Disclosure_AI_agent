from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from itertools import islice
from pathlib import Path
from typing import Any

import psycopg

from evidence.document_relation import DocumentRelation
from evidence.loader import DEFAULT_DATABASE_URL, read_sql

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RELATIONS_PATH = PROJECT_ROOT / "outputs" / "relations" / "relations.jsonl"
ALLOWED_UNRESOLVED_REASONS = frozenset({"no_in_corpus_candidate", "reviewed_no_match"})


def read_relations(path: Path) -> tuple[DocumentRelation, ...]:
    """Read and validate one complete relation snapshot."""

    relations: list[DocumentRelation] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value: Any = json.loads(line)
            relation = DocumentRelation.model_validate(value)
        except Exception as error:
            raise ValueError(f"invalid relation line {line_number}: {error}") from error
        relations.append(relation)

    unique = tuple(dict.fromkeys(relations))
    if len(unique) != len(relations):
        raise ValueError("relation snapshot contains duplicate edges")
    return unique


def validate_unresolved_for_load(path: Path) -> Mapping[str, int]:
    """Allow known absence outcomes but reject unreviewed ambiguity."""

    counts: Counter[str] = Counter()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value: Any = json.loads(line)
        except Exception as error:
            raise ValueError(f"invalid unresolved line {line_number}: {error}") from error
        if not isinstance(value, dict) or not isinstance(value.get("reason"), str):
            raise ValueError(f"invalid unresolved line {line_number}: missing reason")
        counts[value["reason"]] += 1

    blocking = set(counts) - ALLOWED_UNRESOLVED_REASONS
    if blocking:
        details = {reason: counts[reason] for reason in sorted(blocking)}
        raise ValueError(f"relation snapshot has blocking unresolved outcomes: {details}")
    return dict(sorted(counts.items()))


def _relation_rows(relations: Iterable[DocumentRelation]) -> Iterator[dict[str, object]]:
    for relation in relations:
        canonical = relation.model_dump_json()
        yield {
            "relation_id": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "source_doc_id": relation.source_doc_id,
            "source_grain_ids": list(relation.source_grain_ids),
            "predicate": relation.predicate.value,
            "target_doc_id": relation.target_doc_id,
            "target_grain_ids": list(relation.target_grain_ids),
        }


def _batches(
    rows: Iterator[dict[str, object]],
    batch_size: int,
) -> Iterator[list[dict[str, object]]]:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    while batch := list(islice(rows, batch_size)):
        yield batch


def _validate_loaded_grain_endpoints(cursor: psycopg.Cursor[Any]) -> None:
    cursor.execute(
        """
        SELECT
            relation.source_doc_id,
            relation.predicate,
            relation.target_doc_id,
            endpoint.endpoint,
            endpoint.grain_id,
            endpoint.expected_doc_id,
            grain.doc_id AS actual_doc_id
        FROM corpus.document_relation AS relation
        CROSS JOIN LATERAL (
            SELECT
                'source'::text AS endpoint,
                relation.source_doc_id AS expected_doc_id,
                unnest(relation.source_grain_ids) AS grain_id
            UNION ALL
            SELECT
                'target'::text AS endpoint,
                relation.target_doc_id AS expected_doc_id,
                unnest(relation.target_grain_ids) AS grain_id
        ) AS endpoint
        LEFT JOIN corpus.document_grain AS grain
            ON grain.grain_id = endpoint.grain_id
        WHERE grain.grain_id IS NULL OR grain.doc_id <> endpoint.expected_doc_id
        LIMIT 20
        """
    )
    invalid = cursor.fetchall()
    if invalid:
        raise RuntimeError(
            "relation grain endpoints do not match corpus.document_grain; "
            f"reload grains with the same compiler settings first: {invalid}"
        )


def _validate_relation_invariants(cursor: psycopg.Cursor[Any]) -> None:
    cursor.execute(
        """
        SELECT source_doc_id, array_agg(target_doc_id ORDER BY target_doc_id)
          FROM corpus.document_relation
         WHERE predicate = 'revises'
         GROUP BY source_doc_id
        HAVING count(*) > 1
         LIMIT 20
        """
    )
    duplicates = cursor.fetchall()
    if duplicates:
        raise RuntimeError(
            f"a revising document must have exactly one immediate predecessor: {duplicates}"
        )

    cursor.execute(
        """
        SELECT relation.source_doc_id, relation.target_doc_id,
               newer.receipt_date, newer.receipt_no,
               older.receipt_date, older.receipt_no
          FROM corpus.document_relation AS relation
          JOIN corpus.disclosure_document AS newer
            ON newer.doc_id = relation.source_doc_id
          JOIN corpus.disclosure_document AS older
            ON older.doc_id = relation.target_doc_id
         WHERE relation.predicate = 'revises'
           AND (older.receipt_date, older.receipt_no)
               >= (newer.receipt_date, newer.receipt_no)
         LIMIT 20
        """
    )
    chronology_errors = cursor.fetchall()
    if chronology_errors:
        raise RuntimeError(
            f"a revises target must be strictly older than its source: {chronology_errors}"
        )

    cursor.execute(
        """
        WITH RECURSIVE revision_walk AS (
            SELECT source_doc_id AS origin_doc_id,
                   target_doc_id AS current_doc_id,
                   ARRAY[source_doc_id, target_doc_id] AS path,
                   false AS has_cycle
              FROM corpus.document_relation
             WHERE predicate = 'revises'
            UNION ALL
            SELECT walk.origin_doc_id,
                   relation.target_doc_id,
                   walk.path || relation.target_doc_id,
                   relation.target_doc_id = ANY(walk.path)
              FROM revision_walk AS walk
              JOIN corpus.document_relation AS relation
                ON relation.source_doc_id = walk.current_doc_id
               AND relation.predicate = 'revises'
             WHERE NOT walk.has_cycle
        )
        SELECT path
          FROM revision_walk
         WHERE has_cycle
         LIMIT 20
        """
    )
    cycles = cursor.fetchall()
    if cycles:
        raise RuntimeError(f"revises graph must be acyclic: {cycles}")


def replace_document_relations(
    database_url: str,
    relations: Sequence[DocumentRelation],
    *,
    batch_size: int = 500,
) -> int:
    """Replace the DB relation snapshot atomically after endpoint validation."""

    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    create_sql = read_sql("011_create_document_relation.sql")
    insert_sql = read_sql("012_insert_document_relation.sql")

    with psycopg.connect(database_url) as connection:
        connection.execute(create_sql)
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM corpus.document_relation")
            for batch in _batches(_relation_rows(relations), batch_size):
                cursor.executemany(insert_sql, batch)

            _validate_loaded_grain_endpoints(cursor)
            _validate_relation_invariants(cursor)
            cursor.execute("SELECT count(*) FROM corpus.document_relation")
            row = cursor.fetchone()
            loaded = int(row[0]) if row is not None else -1
            if loaded != len(relations):
                raise RuntimeError(
                    "document relation count mismatch after load: "
                    f"expected={len(relations)} actual={loaded}"
                )
    return loaded


def predicate_counts(relations: Iterable[DocumentRelation]) -> Mapping[str, int]:
    counts = Counter(relation.predicate.value for relation in relations)
    return dict(sorted(counts.items()))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Atomically replace corpus.document_relation from relations.jsonl."
    )
    parser.add_argument("--relations-path", type=Path, default=DEFAULT_RELATIONS_PATH)
    parser.add_argument(
        "--unresolved-path",
        type=Path,
        help="Defaults to unresolved.jsonl beside --relations-path.",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Required acknowledgement that the current relation snapshot will be replaced.",
    )
    arguments = parser.parse_args()
    if not arguments.replace:
        parser.error("--replace is required because this command replaces the full edge snapshot")

    unresolved_path = (
        arguments.unresolved_path
        if arguments.unresolved_path is not None
        else arguments.relations_path.with_name("unresolved.jsonl")
    )
    unresolved = validate_unresolved_for_load(unresolved_path)
    relations = read_relations(arguments.relations_path)
    loaded = replace_document_relations(
        arguments.database_url,
        relations,
        batch_size=arguments.batch_size,
    )
    print(
        json.dumps(
            {
                "relations": loaded,
                "predicates": predicate_counts(relations),
                "unresolved": unresolved,
                "relations_path": str(arguments.relations_path.resolve()),
                "unresolved_path": str(unresolved_path.resolve()),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

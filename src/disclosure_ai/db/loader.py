"""Idempotent PostgreSQL loaders for structured corpus data and completed semantic IR."""

from __future__ import annotations

import argparse
import base64
import json
import os
import time
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.types.json import Jsonb

from disclosure_ai.db.derived_reader import iter_verified_entries, read_verified_ir
from disclosure_ai.db.structured import (
    name_aliases,
    normalize_forms,
    read_companies,
    read_documents,
)

DEFAULT_DATABASE_URL = "postgresql://disclosure_ai:local-dev-only@localhost:5432/disclosure_ai"


@dataclass(frozen=True, slots=True)
class LoadSummary:
    companies: int = 0
    documents: int = 0
    artifacts_loaded: int = 0
    artifacts_skipped: int = 0
    sections: int = 0
    semantic_fields: int = 0
    blocks: int = 0
    rows: int = 0
    cells: int = 0
    elapsed_seconds: float = 0.0


def apply_migrations(connection: Connection[Any]) -> None:
    migration_root = Path(__file__).with_name("migrations")
    with connection.cursor() as cursor:
        cursor.execute("CREATE SCHEMA IF NOT EXISTS disclosure")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS disclosure.schema_migration (
                version text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    connection.commit()
    for path in sorted(migration_root.glob("*.sql")):
        version = path.stem
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM disclosure.schema_migration WHERE version = %s)",
                (version,),
            )
            applied = cursor.fetchone()
            if applied is None:
                raise RuntimeError("migration state query returned no row")
            if applied[0]:
                continue
            cursor.execute(path.read_text(encoding="utf-8"))
            cursor.execute(
                """
                INSERT INTO disclosure.schema_migration (version)
                VALUES (%s)
                ON CONFLICT (version) DO NOTHING
                """,
                (version,),
            )
    connection.commit()


def load_structured(connection: Connection[Any], corpus_root: Path | str) -> LoadSummary:
    started = time.monotonic()
    companies = list(read_companies(corpus_root))
    documents = list(read_documents(corpus_root))
    corp_codes = {str(company["corp_code"]) for company in companies}
    unknown = sorted({str(document["corp_code"]) for document in documents} - corp_codes)
    if unknown:
        raise ValueError(f"manifest references unknown corp_code values: {unknown}")

    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.executemany(_COMPANY_UPSERT, [_company_params(company) for company in companies])
            aliases = [alias for company in companies for alias in name_aliases(company)]
            cursor.executemany(_ALIAS_UPSERT, aliases)
            cursor.executemany(
                _DOCUMENT_UPSERT, [_document_params(document) for document in documents]
            )

    return LoadSummary(
        companies=len(companies),
        documents=len(documents),
        elapsed_seconds=round(time.monotonic() - started, 3),
    )


def load_derived(
    connection: Connection[Any],
    corpus_root: Path | str,
    *,
    force: bool = False,
    progress_every: int = 25,
) -> LoadSummary:
    started = time.monotonic()
    existing = _loaded_hashes(connection)
    counts = {
        "artifacts_loaded": 0,
        "artifacts_skipped": 0,
        "sections": 0,
        "semantic_fields": 0,
        "blocks": 0,
        "rows": 0,
        "cells": 0,
    }

    for ordinal, (index, target) in enumerate(iter_verified_entries(corpus_root), start=1):
        source_path = str(index["source_path"])
        derived_sha256 = str(index["derived_sha256"])
        if not force and existing.get(source_path) == derived_sha256:
            counts["artifacts_skipped"] += 1
            continue
        ir = read_verified_ir(index, target)
        _load_ir_artifact(connection, index, ir)
        counts["artifacts_loaded"] += 1
        counts["sections"] += len(ir["sections"])
        counts["semantic_fields"] += len(ir["semantic_fields"])
        counts["blocks"] += len(ir["blocks"])
        counts["rows"] += sum(len(block.get("rows", [])) for block in ir["blocks"])
        counts["cells"] += sum(
            len(row["cells"]) for block in ir["blocks"] for row in block.get("rows", [])
        )
        if progress_every > 0 and ordinal % progress_every == 0:
            elapsed = time.monotonic() - started
            print(
                f"artifacts_seen={ordinal} loaded={counts['artifacts_loaded']} "
                f"skipped={counts['artifacts_skipped']} elapsed={elapsed:.1f}s",
                flush=True,
            )

    return LoadSummary(
        **counts,
        elapsed_seconds=round(time.monotonic() - started, 3),
    )


def _load_ir_artifact(
    connection: Connection[Any], index: dict[str, Any], ir: dict[str, Any]
) -> None:
    source = ir["source"]
    metadata = ir["document_metadata"]
    source_path = str(source["relative_path"])
    path_nfc, path_nfd = normalize_forms(source_path)
    file_nfc, file_nfd = normalize_forms(str(source["file_name"]))
    corp_nfc, corp_nfd = normalize_forms(source.get("corp_folder"))
    source_params = {
        "source_path": source_path,
        "source_path_nfc": path_nfc,
        "source_path_nfd": path_nfd,
        "source_path_bytes": base64.b64decode(source["relative_path_bytes_base64"]),
        "doc_id": metadata["doc_id"],
        "doc_group": source["doc_group"],
        "receipt_no": source["receipt_no"],
        "corp_folder": source.get("corp_folder"),
        "corp_folder_nfc": corp_nfc,
        "corp_folder_nfd": corp_nfd,
        "receipt_folder": source.get("receipt_folder"),
        "file_name": source["file_name"],
        "file_name_nfc": file_nfc,
        "file_name_nfd": file_nfd,
        "file_name_bytes": base64.b64decode(source["file_name_bytes_base64"]),
        "file_role": source["file_role"],
        "attachment_code": source.get("attachment_code"),
        "source_sha256": bytes.fromhex(str(source["sha256"])),
        "source_byte_size": source["byte_size"],
        "detected_format": source["detected_format"],
        "detected_encoding": source.get("detected_encoding"),
        "declared_encoding": source.get("declared_encoding"),
        "derived_path": index["derived_path"],
        "derived_sha256": bytes.fromhex(str(index["derived_sha256"])),
        "derived_byte_size": index["derived_byte_size"],
        "schema_version": ir["schema_version"],
    }

    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(_SOURCE_UPSERT, source_params)
            if source.get("corp_folder"):
                cursor.execute(
                    _ALIAS_UPSERT,
                    {
                        "entity_type": "company",
                        "entity_key": str(metadata["corp_code"]),
                        "name_kind": "raw_corp_folder",
                        "name_raw": source["corp_folder"],
                        "name_nfc": corp_nfc,
                        "name_nfd": corp_nfd,
                    },
                )
            cursor.execute(
                "DELETE FROM disclosure.semantic_ir WHERE source_path = %s", (source_path,)
            )
            cursor.execute(
                _IR_INSERT,
                {
                    "source_path": source_path,
                    "schema_version": ir["schema_version"],
                    "header": Jsonb(ir["header"]),
                    "projection_contract": Jsonb(ir["projection_contract"]),
                    "diagnostics": Jsonb(ir["diagnostics"]),
                    "section_count": len(ir["sections"]),
                    "semantic_field_count": len(ir["semantic_fields"]),
                    "block_count": len(ir["blocks"]),
                },
            )
            cursor.executemany(
                _SECTION_INSERT,
                [_section_params(source_path, section) for section in ir["sections"]],
            )
            cursor.executemany(
                _FIELD_INSERT,
                [_field_params(source_path, field) for field in ir["semantic_fields"]],
            )
            cursor.executemany(
                _BLOCK_INSERT,
                [_block_params(source_path, block) for block in ir["blocks"]],
            )
            rows = [
                _row_params(source_path, block["id"], row)
                for block in ir["blocks"]
                for row in block.get("rows", [])
            ]
            cursor.executemany(_ROW_INSERT, rows)
            cells = [
                _cell_params(source_path, block["id"], row["index"], cell)
                for block in ir["blocks"]
                for row in block.get("rows", [])
                for cell in row["cells"]
            ]
            cursor.executemany(_CELL_INSERT, cells)


def _loaded_hashes(connection: Connection[Any]) -> dict[str, str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT source_path, encode(derived_sha256, 'hex') FROM disclosure.source_artifact"
        )
        result = {str(path): str(digest) for path, digest in cursor.fetchall()}
    connection.commit()
    return result


def _company_params(value: dict[str, Any]) -> dict[str, Any]:
    return {**value, "source_record": Jsonb(value["source_record"])}


def _document_params(value: dict[str, Any]) -> dict[str, Any]:
    return {**value, "source_record": Jsonb(value["source_record"])}


def _section_params(source_path: str, value: dict[str, Any]) -> dict[str, Any]:
    title_nfc, title_nfd = normalize_forms(value.get("title"))
    return {
        "source_path": source_path,
        "section_id": value["id"],
        "ordinal": value["ordinal"],
        "parent_section_id": value.get("parent_section_id"),
        "level": value.get("level"),
        "source_element": value.get("source_element"),
        "title": value.get("title"),
        "title_nfc": title_nfc,
        "title_nfd": title_nfd,
        "attributes": Jsonb(value.get("attributes", [])),
        **value["evidence"],
    }


def _field_params(source_path: str, value: dict[str, Any]) -> dict[str, Any]:
    text_nfc, text_nfd = normalize_forms(value.get("text"))
    return {
        "source_path": source_path,
        "field_id": value["id"],
        "ordinal": value["ordinal"],
        "section_id": value.get("section_id"),
        "element": value["element"],
        "key_type": value.get("key_type"),
        "semantic_key": value.get("key"),
        "display_text": value.get("text"),
        "display_text_nfc": text_nfc,
        "display_text_nfd": text_nfd,
        "machine_value": value.get("machine_value"),
        "value_type": value["value_type"],
        "attributes": Jsonb(value.get("attributes", [])),
        **value["evidence"],
    }


def _block_params(source_path: str, value: dict[str, Any]) -> dict[str, Any]:
    text_nfc, text_nfd = normalize_forms(value.get("text"))
    return {
        "source_path": source_path,
        "block_id": value["id"],
        "ordinal": value["ordinal"],
        "section_id": value.get("section_id"),
        "kind": value["kind"],
        "parent_table_id": value.get("parent_table_id"),
        "text_value": value.get("text"),
        "text_value_nfc": text_nfc,
        "text_value_nfd": text_nfd,
        "classification": value.get("classification"),
        "message": value.get("message"),
        "table_class": value.get("table_class"),
        "table_group_class": value.get("table_group_class"),
        "attributes": Jsonb(value.get("attributes", [])),
        **value["evidence"],
    }


def _row_params(source_path: str, block_id: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_path": source_path,
        "block_id": block_id,
        "row_index": value["index"],
        **value["evidence"],
    }


def _cell_params(
    source_path: str, block_id: str, row_index: int, value: dict[str, Any]
) -> dict[str, Any]:
    text_nfc, text_nfd = normalize_forms(value.get("text"))
    labels = [str(label) for label in value.get("context_labels", [])]
    return {
        "source_path": source_path,
        "block_id": block_id,
        "row_index": row_index,
        "column_index": value["column_index"],
        "cell_id": value["id"],
        "rowspan": value["rowspan"],
        "colspan": value["colspan"],
        "element": value.get("element"),
        "role": value["role"],
        "semantic_key": value.get("semantic_key"),
        "machine_value": value.get("machine_value"),
        "value_type": value["value_type"],
        "display_text": value.get("text"),
        "display_text_nfc": text_nfc,
        "display_text_nfd": text_nfd,
        "context_labels": labels,
        "context_labels_nfc": [unicodedata.normalize("NFC", label) for label in labels],
        "context_labels_nfd": [unicodedata.normalize("NFD", label) for label in labels],
        "attributes": Jsonb(value.get("attributes", [])),
        **value["evidence"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("structured", "derived", "all"))
    parser.add_argument("corpus", nargs="?", default="corpus")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    parser.add_argument("--force", action="store_true", help="reload unchanged derived artifacts")
    parser.add_argument("--progress-every", type=int, default=25)
    args = parser.parse_args()

    with psycopg.connect(args.database_url) as connection:
        apply_migrations(connection)
        results: dict[str, Any] = {}
        if args.command in {"structured", "all"}:
            results["structured"] = asdict(load_structured(connection, args.corpus))
        if args.command in {"derived", "all"}:
            results["derived"] = asdict(
                load_derived(
                    connection,
                    args.corpus,
                    force=args.force,
                    progress_every=args.progress_every,
                )
            )
    print(json.dumps(results, ensure_ascii=False, indent=2))


_COMPANY_COLUMNS = (
    "corp_code",
    "stock_code",
    "corp_name",
    "corp_name_nfc",
    "corp_name_nfd",
    "listed_name",
    "listed_name_nfc",
    "listed_name_nfd",
    "corp_eng_name",
    "market",
    "industry",
    "sector_no",
    "sector",
    "listing_date",
    "fiscal_month",
    "market_cap",
    "n_periodic",
    "n_major",
    "n_exchange",
    "n_holding",
    "note",
    "source_record",
)
_COMPANY_UPDATES = ", ".join(
    f"{column} = EXCLUDED.{column}" for column in _COMPANY_COLUMNS if column != "corp_code"
)
_COMPANY_UPSERT = f"""
INSERT INTO disclosure.company ({", ".join(_COMPANY_COLUMNS)})
VALUES ({", ".join(f"%({column})s" for column in _COMPANY_COLUMNS)})
ON CONFLICT (corp_code) DO UPDATE SET
{_COMPANY_UPDATES},
updated_at = now()
"""

_ALIAS_UPSERT = """
INSERT INTO disclosure.name_alias
    (entity_type, entity_key, name_kind, name_raw, name_nfc, name_nfd)
VALUES
    (%(entity_type)s, %(entity_key)s, %(name_kind)s, %(name_raw)s, %(name_nfc)s, %(name_nfd)s)
ON CONFLICT (entity_type, entity_key, name_kind, name_raw) DO UPDATE SET
    name_nfc = EXCLUDED.name_nfc,
    name_nfd = EXCLUDED.name_nfd
"""

_DOCUMENT_COLUMNS = (
    "doc_id",
    "corp_code",
    "corp_name",
    "corp_name_nfc",
    "corp_name_nfd",
    "listed_name",
    "stock_code",
    "industry",
    "sector",
    "doc_group",
    "doc_subtype",
    "report_nm",
    "report_nm_nfc",
    "report_nm_nfd",
    "is_correction",
    "rcept_no",
    "rcept_dt",
    "flr_nm",
    "flr_nm_nfc",
    "flr_nm_nfd",
    "base_year",
    "base_month",
    "file_path",
    "file_path_nfc",
    "file_path_nfd",
    "file_format",
    "n_files",
    "source_record",
)
_DOCUMENT_UPSERT = f"""
INSERT INTO disclosure.disclosure_document ({", ".join(_DOCUMENT_COLUMNS)})
VALUES ({", ".join(f"%({column})s" for column in _DOCUMENT_COLUMNS)})
ON CONFLICT (doc_id) DO UPDATE SET
{", ".join(f"{column} = EXCLUDED.{column}" for column in _DOCUMENT_COLUMNS if column != "doc_id")},
updated_at = now()
"""

_SOURCE_COLUMNS = (
    "source_path",
    "source_path_nfc",
    "source_path_nfd",
    "source_path_bytes",
    "doc_id",
    "doc_group",
    "receipt_no",
    "corp_folder",
    "corp_folder_nfc",
    "corp_folder_nfd",
    "receipt_folder",
    "file_name",
    "file_name_nfc",
    "file_name_nfd",
    "file_name_bytes",
    "file_role",
    "attachment_code",
    "source_sha256",
    "source_byte_size",
    "detected_format",
    "detected_encoding",
    "declared_encoding",
    "derived_path",
    "derived_sha256",
    "derived_byte_size",
    "schema_version",
)
_SOURCE_UPDATES = ", ".join(
    f"{column} = EXCLUDED.{column}" for column in _SOURCE_COLUMNS if column != "source_path"
)
_SOURCE_UPSERT = f"""
INSERT INTO disclosure.source_artifact ({", ".join(_SOURCE_COLUMNS)})
VALUES ({", ".join(f"%({column})s" for column in _SOURCE_COLUMNS)})
ON CONFLICT (source_path) DO UPDATE SET
{_SOURCE_UPDATES},
loaded_at = now()
"""

_IR_INSERT = """
INSERT INTO disclosure.semantic_ir
    (source_path, schema_version, header, projection_contract, diagnostics,
     section_count, semantic_field_count, block_count)
VALUES
    (%(source_path)s, %(schema_version)s, %(header)s, %(projection_contract)s, %(diagnostics)s,
     %(section_count)s, %(semantic_field_count)s, %(block_count)s)
"""

_SECTION_INSERT = """
INSERT INTO disclosure.semantic_section
    (source_path, section_id, ordinal, parent_section_id, level, source_element, title,
     title_nfc, title_nfd, attributes, start_byte, end_byte)
VALUES
    (%(source_path)s, %(section_id)s, %(ordinal)s, %(parent_section_id)s, %(level)s,
     %(source_element)s, %(title)s, %(title_nfc)s, %(title_nfd)s, %(attributes)s,
     %(start_byte)s, %(end_byte)s)
"""

_FIELD_INSERT = """
INSERT INTO disclosure.semantic_field
    (source_path, field_id, ordinal, section_id, element, key_type, semantic_key,
     display_text, display_text_nfc, display_text_nfd, machine_value, value_type, attributes,
     start_byte, end_byte)
VALUES
    (%(source_path)s, %(field_id)s, %(ordinal)s, %(section_id)s, %(element)s, %(key_type)s,
     %(semantic_key)s, %(display_text)s, %(display_text_nfc)s, %(display_text_nfd)s,
     %(machine_value)s, %(value_type)s, %(attributes)s, %(start_byte)s, %(end_byte)s)
"""

_BLOCK_INSERT = """
INSERT INTO disclosure.semantic_block
    (source_path, block_id, ordinal, section_id, kind, parent_table_id, text_value,
     text_value_nfc, text_value_nfd, classification, message, table_class, table_group_class,
     attributes, start_byte, end_byte)
VALUES
    (%(source_path)s, %(block_id)s, %(ordinal)s, %(section_id)s, %(kind)s,
     %(parent_table_id)s, %(text_value)s, %(text_value_nfc)s, %(text_value_nfd)s,
     %(classification)s, %(message)s, %(table_class)s, %(table_group_class)s,
     %(attributes)s, %(start_byte)s, %(end_byte)s)
"""

_ROW_INSERT = """
INSERT INTO disclosure.semantic_table_row
    (source_path, block_id, row_index, start_byte, end_byte)
VALUES
    (%(source_path)s, %(block_id)s, %(row_index)s, %(start_byte)s, %(end_byte)s)
"""

_CELL_INSERT = """
INSERT INTO disclosure.semantic_cell
    (source_path, block_id, row_index, column_index, cell_id, rowspan, colspan, element,
     role, semantic_key, machine_value, value_type, display_text, display_text_nfc,
     display_text_nfd, context_labels, context_labels_nfc, context_labels_nfd, attributes,
     start_byte, end_byte)
VALUES
    (%(source_path)s, %(block_id)s, %(row_index)s, %(column_index)s, %(cell_id)s,
     %(rowspan)s, %(colspan)s, %(element)s, %(role)s, %(semantic_key)s, %(machine_value)s,
     %(value_type)s, %(display_text)s, %(display_text_nfc)s, %(display_text_nfd)s,
     %(context_labels)s, %(context_labels_nfc)s, %(context_labels_nfd)s, %(attributes)s,
     %(start_byte)s, %(end_byte)s)
"""


if __name__ == "__main__":
    main()

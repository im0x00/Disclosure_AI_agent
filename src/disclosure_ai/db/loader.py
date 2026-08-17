"""Idempotent PostgreSQL loaders for structured corpus data and completed semantic IR."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import threading
import time
import unicodedata
import uuid
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
_VACUUM_TABLES = frozenset(
    {
        "disclosure.semantic_section",
        "disclosure.semantic_field",
        "disclosure.semantic_block",
        "disclosure.semantic_table_row",
        "disclosure.semantic_cell",
    }
)


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


@dataclass(frozen=True, slots=True)
class MigrationStep:
    label: str
    statement: str
    vacuum_table: str | None = None
    vacuum_every: int = 1


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
                print(f"migration={version} status=skipped", flush=True)
                continue
        connection.commit()
        steps = _migration_steps(path.read_text(encoding="utf-8"))
        for step_number, step in enumerate(steps, start=1):
            progress = f"migration={version} step={step_number}/{len(steps)} phase={step.label}"
            if step.vacuum_table is None:
                with connection.cursor() as cursor:
                    _execute_with_heartbeat(cursor, step.statement, progress)
                connection.commit()
            else:
                _execute_batched_migration_step(connection, step, progress)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO disclosure.schema_migration (version)
                VALUES (%s)
                ON CONFLICT (version) DO NOTHING
                """,
                (version,),
            )
        connection.commit()
    connection.commit()


def _migration_steps(migration: str) -> list[MigrationStep]:
    progress_marker = "-- progress: "
    batch_marker = "-- progress-batch: "
    steps: list[MigrationStep] = []
    current = MigrationStep(label="apply", statement="")
    lines: list[str] = []

    for line in migration.splitlines(keepends=True):
        if line.startswith(progress_marker) or line.startswith(batch_marker):
            statement = "".join(lines).strip()
            if statement:
                steps.append(
                    MigrationStep(
                        label=current.label,
                        statement=statement,
                        vacuum_table=current.vacuum_table,
                        vacuum_every=current.vacuum_every,
                    )
                )
            if line.startswith(batch_marker):
                payload = line.removeprefix(batch_marker).strip().split("|")
                if len(payload) != 3:
                    raise ValueError(f"invalid batched migration marker: {line.strip()}")
                label, vacuum_table, vacuum_every = payload
                if vacuum_table not in _VACUUM_TABLES:
                    raise ValueError(f"unsupported vacuum table: {vacuum_table}")
                vacuum_every_value = int(vacuum_every)
                if vacuum_every_value <= 0:
                    raise ValueError("vacuum frequency must be positive")
                current = MigrationStep(
                    label=label,
                    statement="",
                    vacuum_table=vacuum_table,
                    vacuum_every=vacuum_every_value,
                )
            else:
                current = MigrationStep(
                    label=line.removeprefix(progress_marker).strip(), statement=""
                )
            lines = []
        else:
            lines.append(line)

    statement = "".join(lines).strip()
    if statement:
        steps.append(
            MigrationStep(
                label=current.label,
                statement=statement,
                vacuum_table=current.vacuum_table,
                vacuum_every=current.vacuum_every,
            )
        )
    return steps


def _execute_batched_migration_step(
    connection: Connection[Any], step: MigrationStep, progress: str
) -> None:
    total_rows = 0
    batch_number = 0
    while True:
        batch_number += 1
        with connection.cursor() as cursor:
            _execute_with_heartbeat(cursor, step.statement, f"{progress} batch={batch_number}")
            affected_rows = cursor.rowcount
        connection.commit()
        if affected_rows <= 0:
            break
        total_rows += affected_rows
        print(
            f"{progress} status=committed batch={batch_number} "
            f"rows={affected_rows} total_rows={total_rows}",
            flush=True,
        )
        if batch_number % step.vacuum_every == 0:
            _vacuum_after_batch(connection, step.vacuum_table, progress)

    completed_batches = batch_number - 1
    if total_rows and completed_batches % step.vacuum_every != 0:
        _vacuum_after_batch(connection, step.vacuum_table, progress)
    print(f"{progress} status=completed total_rows={total_rows}", flush=True)


def _vacuum_after_batch(connection: Connection[Any], table: str | None, progress: str) -> None:
    if table is None:
        return
    previous_autocommit = connection.autocommit
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            _execute_with_heartbeat(cursor, f"VACUUM {table}", f"{progress} vacuum={table}")
    finally:
        connection.autocommit = previous_autocommit


def _execute_with_heartbeat(cursor: Any, statement: str, progress: str) -> None:
    started = time.monotonic()
    stopped = threading.Event()

    def heartbeat() -> None:
        while not stopped.wait(10):
            elapsed = time.monotonic() - started
            print(f"{progress} status=running elapsed={elapsed:.1f}s", flush=True)

    print(f"{progress} status=started", flush=True)
    worker = threading.Thread(target=heartbeat, daemon=True)
    worker.start()
    try:
        cursor.execute(statement)
    except BaseException:
        elapsed = time.monotonic() - started
        print(f"{progress} status=failed elapsed={elapsed:.1f}s", flush=True)
        raise
    else:
        elapsed = time.monotonic() - started
        print(f"{progress} status=completed elapsed={elapsed:.1f}s", flush=True)
    finally:
        stopped.set()
        worker.join()


def load_structured(connection: Connection[Any], corpus_root: Path | str) -> LoadSummary:
    started = time.monotonic()
    print("structured phase=read_sources status=started", flush=True)
    companies = list(read_companies(corpus_root))
    documents = list(read_documents(corpus_root))
    print(
        f"structured phase=read_sources status=completed companies={len(companies)} "
        f"documents={len(documents)}",
        flush=True,
    )
    corp_codes = {str(company["corp_code"]) for company in companies}
    unknown = sorted({str(document["corp_code"]) for document in documents} - corp_codes)
    if unknown:
        raise ValueError(f"manifest references unknown corp_code values: {unknown}")

    with connection.transaction():
        with connection.cursor() as cursor:
            print("structured phase=upsert_companies status=started", flush=True)
            cursor.executemany(_COMPANY_UPSERT, [_company_params(company) for company in companies])
            aliases = [alias for company in companies for alias in name_aliases(company)]
            cursor.executemany(_ALIAS_UPSERT, aliases)
            print("structured phase=upsert_companies status=completed", flush=True)
            print("structured phase=upsert_documents status=started", flush=True)
            cursor.executemany(
                _DOCUMENT_UPSERT, [_document_params(document) for document in documents]
            )
            print("structured phase=upsert_documents status=completed", flush=True)

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
                _DELETE_ARTIFACT_NODES,
                {"source_path": source_path},
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
                _NODE_UPSERT,
                _node_params(source_path, str(metadata["doc_id"]), ir),
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
        "node_id": _node_id(source_path, "section", str(value["id"])),
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
        "node_id": _node_id(source_path, "field", str(value["id"])),
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
        "node_id": _node_id(source_path, "block", str(value["id"])),
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
        "node_id": _row_node_id(source_path, block_id, int(value["index"])),
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
        "node_id": _node_id(source_path, "cell", str(value["id"])),
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


def _node_id(source_path: str, node_type: str, local_id: str) -> uuid.UUID:
    address = "\x1f".join((source_path, node_type, local_id))
    digest = hashlib.md5(address.encode("utf-8"), usedforsecurity=False).digest()
    return uuid.UUID(bytes=digest)


def _row_node_id(source_path: str, block_id: str, row_index: int) -> uuid.UUID:
    return _node_id(source_path, "table_row", f"{block_id}:{row_index}")


def _node_params(source_path: str, document_id: str, ir: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    for section in ir["sections"]:
        parent_section_id = section.get("parent_section_id")
        nodes.append(
            {
                "node_id": _node_id(source_path, "section", str(section["id"])),
                "document_id": document_id,
                "node_type": "section",
                "parent_node_id": (
                    _node_id(source_path, "section", str(parent_section_id))
                    if parent_section_id is not None
                    else None
                ),
                "ordinal": section["ordinal"],
            }
        )

    for field in ir["semantic_fields"]:
        section_id = field.get("section_id")
        nodes.append(
            {
                "node_id": _node_id(source_path, "field", str(field["id"])),
                "document_id": document_id,
                "node_type": "field",
                "parent_node_id": (
                    _node_id(source_path, "section", str(section_id))
                    if section_id is not None
                    else None
                ),
                "ordinal": field["ordinal"],
            }
        )

    for block in ir["blocks"]:
        parent_table_id = block.get("parent_table_id")
        section_id = block.get("section_id")
        if parent_table_id is not None:
            parent_node_id = _node_id(source_path, "block", str(parent_table_id))
        elif section_id is not None:
            parent_node_id = _node_id(source_path, "section", str(section_id))
        else:
            parent_node_id = None
        nodes.append(
            {
                "node_id": _node_id(source_path, "block", str(block["id"])),
                "document_id": document_id,
                "node_type": "block",
                "parent_node_id": parent_node_id,
                "ordinal": block["ordinal"],
            }
        )

        for row in block.get("rows", []):
            row_node_id = _row_node_id(source_path, str(block["id"]), int(row["index"]))
            nodes.append(
                {
                    "node_id": row_node_id,
                    "document_id": document_id,
                    "node_type": "table_row",
                    "parent_node_id": _node_id(source_path, "block", str(block["id"])),
                    "ordinal": row["index"],
                }
            )
            nodes.extend(
                {
                    "node_id": _node_id(source_path, "cell", str(cell["id"])),
                    "document_id": document_id,
                    "node_type": "cell",
                    "parent_node_id": row_node_id,
                    "ordinal": cell["column_index"],
                }
                for cell in row["cells"]
            )

    return nodes


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

_DELETE_ARTIFACT_NODES = """
DELETE FROM disclosure.nodes
WHERE node_id IN (
    SELECT node_id FROM disclosure.semantic_section WHERE source_path = %(source_path)s
    UNION ALL
    SELECT node_id FROM disclosure.semantic_field WHERE source_path = %(source_path)s
    UNION ALL
    SELECT node_id FROM disclosure.semantic_block WHERE source_path = %(source_path)s
    UNION ALL
    SELECT node_id FROM disclosure.semantic_table_row WHERE source_path = %(source_path)s
    UNION ALL
    SELECT node_id FROM disclosure.semantic_cell WHERE source_path = %(source_path)s
)
"""

_NODE_UPSERT = """
INSERT INTO disclosure.nodes (node_id, document_id, node_type, parent_node_id, ordinal)
VALUES (%(node_id)s, %(document_id)s, %(node_type)s, %(parent_node_id)s, %(ordinal)s)
ON CONFLICT (node_id) DO UPDATE SET
    document_id = EXCLUDED.document_id,
    node_type = EXCLUDED.node_type,
    parent_node_id = EXCLUDED.parent_node_id,
    ordinal = EXCLUDED.ordinal
"""

_SECTION_INSERT = """
INSERT INTO disclosure.semantic_section
    (source_path, node_id, section_id, ordinal, parent_section_id, level, source_element, title,
     title_nfc, title_nfd, attributes, start_byte, end_byte)
VALUES
    (%(source_path)s, %(node_id)s, %(section_id)s, %(ordinal)s, %(parent_section_id)s, %(level)s,
     %(source_element)s, %(title)s, %(title_nfc)s, %(title_nfd)s, %(attributes)s,
     %(start_byte)s, %(end_byte)s)
"""

_FIELD_INSERT = """
INSERT INTO disclosure.semantic_field
    (source_path, node_id, field_id, ordinal, section_id, element, key_type, semantic_key,
     display_text, display_text_nfc, display_text_nfd, machine_value, value_type, attributes,
     start_byte, end_byte)
VALUES
    (%(source_path)s, %(node_id)s, %(field_id)s, %(ordinal)s, %(section_id)s, %(element)s,
     %(key_type)s,
     %(semantic_key)s, %(display_text)s, %(display_text_nfc)s, %(display_text_nfd)s,
     %(machine_value)s, %(value_type)s, %(attributes)s, %(start_byte)s, %(end_byte)s)
"""

_BLOCK_INSERT = """
INSERT INTO disclosure.semantic_block
    (source_path, node_id, block_id, ordinal, section_id, kind, parent_table_id, text_value,
     text_value_nfc, text_value_nfd, classification, message, table_class, table_group_class,
     attributes, start_byte, end_byte)
VALUES
    (%(source_path)s, %(node_id)s, %(block_id)s, %(ordinal)s, %(section_id)s, %(kind)s,
     %(parent_table_id)s, %(text_value)s, %(text_value_nfc)s, %(text_value_nfd)s,
     %(classification)s, %(message)s, %(table_class)s, %(table_group_class)s,
     %(attributes)s, %(start_byte)s, %(end_byte)s)
"""

_ROW_INSERT = """
INSERT INTO disclosure.semantic_table_row
    (source_path, node_id, block_id, row_index, start_byte, end_byte)
VALUES
    (%(source_path)s, %(node_id)s, %(block_id)s, %(row_index)s, %(start_byte)s, %(end_byte)s)
"""

_CELL_INSERT = """
INSERT INTO disclosure.semantic_cell
    (source_path, node_id, block_id, row_index, column_index, cell_id, rowspan, colspan, element,
     role, semantic_key, machine_value, value_type, display_text, display_text_nfc,
     display_text_nfd, context_labels, context_labels_nfc, context_labels_nfd, attributes,
     start_byte, end_byte)
VALUES
    (%(source_path)s, %(node_id)s, %(block_id)s, %(row_index)s, %(column_index)s, %(cell_id)s,
     %(rowspan)s, %(colspan)s, %(element)s, %(role)s, %(semantic_key)s, %(machine_value)s,
     %(value_type)s, %(display_text)s, %(display_text_nfc)s, %(display_text_nfd)s,
     %(context_labels)s, %(context_labels_nfc)s, %(context_labels_nfd)s, %(attributes)s,
     %(start_byte)s, %(end_byte)s)
"""


if __name__ == "__main__":
    main()

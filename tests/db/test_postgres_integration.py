from __future__ import annotations

import json
import os
import shutil
import unicodedata
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import Connection, sql

from disclosure_ai.db.derived_reader import completed_derived_root, read_verified_ir
from disclosure_ai.db.loader import apply_migrations, load_derived, load_structured

CORPUS = Path(__file__).resolve().parents[2] / "corpus"
ADMIN_URL_ENV = "DISCLOSURE_TEST_POSTGRES_URL"
AUDIT_SOURCE_PATH = "raw/major/고려아연/20240320001544/20240320001544.xml"


def _database_url(base_url: str, database: str) -> str:
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", parts.query, parts.fragment))


@pytest.fixture(scope="module")
def postgres() -> Iterator[Connection[Any]]:
    admin_url = os.environ.get(ADMIN_URL_ENV)
    if not admin_url:
        pytest.skip(f"set {ADMIN_URL_ENV} to run the PostgreSQL audit")

    database = f"disclosure_audit_{uuid.uuid4().hex}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))

    test_url = _database_url(admin_url, database)
    try:
        with psycopg.connect(test_url) as connection:
            yield connection
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (database,),
                )
                cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))


def test_real_postgres_structured_load_is_exact_and_idempotent(
    postgres: Connection[Any],
) -> None:
    apply_migrations(postgres)
    apply_migrations(postgres)
    first = load_structured(postgres, CORPUS)
    second = load_structured(postgres, CORPUS)

    assert (first.companies, first.documents) == (70, 4204)
    assert (second.companies, second.documents) == (70, 4204)
    with postgres.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM disclosure.company")
        assert cursor.fetchone() == (70,)
        cursor.execute("SELECT count(*) FROM disclosure.disclosure_document")
        assert cursor.fetchone() == (4204,)
        cursor.execute("SELECT count(*) FROM disclosure.name_alias")
        assert cursor.fetchone() == (140,)
        cursor.execute("SELECT count(*) FROM disclosure.schema_migration")
        assert cursor.fetchone() == (3,)
        cursor.execute(
            "SELECT count(*) FROM disclosure.disclosure_document "
            "WHERE corp_name_nfc <> normalize(corp_name, NFC) "
            "OR corp_name_nfd <> normalize(corp_name, NFD)"
        )
        assert cursor.fetchone() == (0,)


def test_real_postgres_loads_verified_ir_and_joins_nfc_nfd(
    postgres: Connection[Any], tmp_path: Path
) -> None:
    source_root = completed_derived_root(CORPUS)
    manifest_lines = (source_root / "manifest.jsonl").read_text().splitlines()
    entries = [json.loads(line) for line in manifest_lines]
    index = next(value for value in entries if value["source_path"] == AUDIT_SOURCE_PATH)
    source_target = source_root / str(index["derived_path"])

    audit_root = tmp_path / "derived" / "semantic-structural-ir-v1"
    target = audit_root / str(index["derived_path"])
    target.parent.mkdir(parents=True)
    shutil.copyfile(source_target, target)
    (audit_root / "manifest.jsonl").write_text(
        json.dumps(index, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    shutil.copyfile(source_root / "_SUCCESS.json", audit_root / "_SUCCESS.json")

    ir = read_verified_ir(index, target)
    first = load_derived(postgres, tmp_path, progress_every=0)
    skipped = load_derived(postgres, tmp_path, progress_every=0)
    forced = load_derived(postgres, tmp_path, force=True, progress_every=0)

    assert first.artifacts_loaded == 1
    assert skipped.artifacts_skipped == 1
    assert forced.artifacts_loaded == 1
    assert first.sections == len(ir["sections"])
    assert first.semantic_fields == len(ir["semantic_fields"])
    assert first.blocks == len(ir["blocks"])
    assert first.rows == sum(len(block.get("rows", [])) for block in ir["blocks"])
    assert first.cells == sum(
        len(row["cells"]) for block in ir["blocks"] for row in block.get("rows", [])
    )

    source_path = str(index["source_path"])
    with postgres.cursor() as cursor:
        cursor.execute(
            "SELECT source_path_bytes, file_name_bytes, encode(source_sha256, 'hex') "
            "FROM disclosure.source_artifact WHERE source_path = %s",
            (source_path,),
        )
        source_row = cursor.fetchone()
        assert source_row is not None
        path_bytes, file_bytes, source_hash = source_row
        assert bytes(path_bytes) == source_path.encode("utf-8")
        assert bytes(file_bytes) == Path(source_path).name.encode("utf-8")
        assert source_hash == index["source_sha256"]

        cursor.execute(
            "SELECT count(*) FROM disclosure.company_artifact_join WHERE source_path = %s",
            (source_path,),
        )
        assert cursor.fetchone() == (1,)
        cursor.execute(
            "SELECT corp_folder, corp_folder_nfc, corp_folder_nfd "
            "FROM disclosure.source_artifact WHERE source_path = %s",
            (source_path,),
        )
        folder_row = cursor.fetchone()
        assert folder_row is not None
        raw, nfc, nfd = folder_row
        assert nfc == unicodedata.normalize("NFC", raw)
        assert nfd == unicodedata.normalize("NFD", raw)

        cursor.execute(
            "SELECT section_count, semantic_field_count, block_count "
            "FROM disclosure.semantic_ir WHERE source_path = %s",
            (source_path,),
        )
        assert cursor.fetchone() == (
            len(ir["sections"]),
            len(ir["semantic_fields"]),
            len(ir["blocks"]),
        )
        for table, expected in (
            ("semantic_section", first.sections),
            ("semantic_field", first.semantic_fields),
            ("semantic_block", first.blocks),
            ("semantic_table_row", first.rows),
            ("semantic_cell", first.cells),
        ):
            cursor.execute(
                sql.SQL("SELECT count(*) FROM disclosure.{} WHERE source_path = %s").format(
                    sql.Identifier(table)
                ),
                (source_path,),
            )
            assert cursor.fetchone() == (expected,)

        expected_nodes = (
            first.sections + first.semantic_fields + first.blocks + first.rows + first.cells
        )
        cursor.execute(
            "SELECT count(*) FROM disclosure.nodes WHERE document_id = %s",
            (str(ir["document_metadata"]["doc_id"]),),
        )
        assert cursor.fetchone() == (expected_nodes,)
        cursor.execute(
            "SELECT count(*) FROM disclosure.nodes AS child "
            "LEFT JOIN disclosure.nodes AS parent ON parent.node_id = child.parent_node_id "
            "WHERE child.parent_node_id IS NOT NULL AND parent.node_id IS NULL"
        )
        assert cursor.fetchone() == (0,)
        cursor.execute(
            "SELECT count(*) FROM disclosure.nodes AS child "
            "JOIN disclosure.nodes AS parent ON parent.node_id = child.parent_node_id "
            "WHERE child.document_id <> parent.document_id"
        )
        assert cursor.fetchone() == (0,)
        cursor.execute(
            "SELECT count(*) FROM ("
            "SELECT node_id, source_path, 'section' AS expected_type "
            "FROM disclosure.semantic_section "
            "UNION ALL SELECT node_id, source_path, 'field' FROM disclosure.semantic_field "
            "UNION ALL SELECT node_id, source_path, 'block' FROM disclosure.semantic_block "
            "UNION ALL SELECT node_id, source_path, 'table_row' "
            "FROM disclosure.semantic_table_row "
            "UNION ALL SELECT node_id, source_path, 'cell' FROM disclosure.semantic_cell"
            ") AS semantic "
            "JOIN disclosure.nodes AS node USING (node_id) "
            "JOIN disclosure.source_artifact AS artifact USING (source_path) "
            "WHERE node.node_type <> semantic.expected_type "
            "OR node.document_id <> artifact.doc_id"
        )
        assert cursor.fetchone() == (0,)

        cursor.execute(
            "SELECT child.node_id, parent.node_id "
            "FROM disclosure.nodes AS child "
            "JOIN disclosure.nodes AS parent ON parent.node_id = child.parent_node_id "
            "WHERE child.document_id = %s LIMIT 1",
            (str(ir["document_metadata"]["doc_id"]),),
        )
        hierarchy_pair = cursor.fetchone()
        assert hierarchy_pair is not None
        child_node_id, parent_node_id = hierarchy_pair
        cursor.execute("SAVEPOINT reject_cycle")
        cursor.execute(
            "UPDATE disclosure.nodes SET parent_node_id = %s WHERE node_id = %s",
            (child_node_id, parent_node_id),
        )
        with pytest.raises(psycopg.errors.RaiseException, match="hierarchy cycle"):
            cursor.execute("SET CONSTRAINTS disclosure.nodes_hierarchy_invariants IMMEDIATE")
        cursor.execute("ROLLBACK TO SAVEPOINT reject_cycle")

        cursor.execute(
            "SELECT node_id FROM disclosure.semantic_section WHERE source_path = %s LIMIT 1",
            (source_path,),
        )
        section_node = cursor.fetchone()
        cursor.execute(
            "SELECT node_id FROM disclosure.semantic_block WHERE source_path = %s LIMIT 1",
            (source_path,),
        )
        block_node = cursor.fetchone()
        assert section_node is not None and block_node is not None
        cursor.execute("SAVEPOINT reject_wrong_type")
        cursor.execute(
            "UPDATE disclosure.semantic_section SET node_id = %s WHERE node_id = %s",
            (block_node[0], section_node[0]),
        )
        with pytest.raises(psycopg.errors.RaiseException, match="expected node type section"):
            cursor.execute(
                "SET CONSTRAINTS disclosure.semantic_section_node_metadata IMMEDIATE"
            )
        cursor.execute("ROLLBACK TO SAVEPOINT reject_wrong_type")

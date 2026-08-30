import json
from pathlib import Path

from reasoning.retrieval.index_scope import load_mini_world, resolve_mini_world


def test_mini_world_applies_relation_closure(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    suite_path = tmp_path / "suite.json"
    cases_path = tmp_path / "cases.jsonl"
    manifest_path = tmp_path / "manifest.jsonl"
    relations_path = tmp_path / "relations.jsonl"
    profile_path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "world_id": "test-world",
                "company_codes": ["00000001"],
                "receipt_date_from": "2024-01-01",
                "receipt_date_to": "2024-12-31",
                "document_selection": {
                    "strategy": "suite_required_documents",
                    "suite_path": "suite.json",
                },
                "relation_closure": {
                    "revises": "both_transitive",
                    "references": "outgoing_one_hop",
                    "terminates": "outgoing_one_hop",
                },
            }
        ),
        encoding="utf-8",
    )
    suite_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "world_id": "test-world",
                "case_count": 1,
                "case_sources": [{"path": "cases.jsonl", "case_ids": ["case:test"]}],
            }
        ),
        encoding="utf-8",
    )
    cases_path.write_text(
        json.dumps(
            {
                "case_id": "case:test",
                "required_document_ids": ["base"],
            }
        ),
        encoding="utf-8",
    )
    documents = [
        {
            "doc_id": "old",
            "corp_code": "00000001",
            "rcept_dt": "20230101",
            "doc_group": "exchange",
        },
        {
            "doc_id": "base",
            "corp_code": "00000001",
            "rcept_dt": "20240601",
            "doc_group": "periodic",
        },
        {
            "doc_id": "new",
            "corp_code": "00000001",
            "rcept_dt": "20250101",
            "doc_group": "exchange",
        },
        {
            "doc_id": "reference",
            "corp_code": "00000002",
            "rcept_dt": "20220101",
            "doc_group": "major",
        },
    ]
    manifest_path.write_text(
        "\n".join(json.dumps(document) for document in documents), encoding="utf-8"
    )
    relations = [
        {"source_doc_id": "base", "predicate": "revises", "target_doc_id": "old"},
        {"source_doc_id": "new", "predicate": "revises", "target_doc_id": "base"},
        {
            "source_doc_id": "new",
            "predicate": "references",
            "target_doc_id": "reference",
        },
    ]
    relations_path.write_text(
        "\n".join(json.dumps(relation) for relation in relations), encoding="utf-8"
    )

    resolution = resolve_mini_world(
        load_mini_world(profile_path),
        profile_path=profile_path,
        manifest_path=manifest_path,
        relations_path=relations_path,
    )

    assert resolution.base_document_count == 1
    assert resolution.closure_document_count == 3
    assert resolution.document_ids == ("base", "new", "old", "reference")

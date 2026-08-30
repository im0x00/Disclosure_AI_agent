from __future__ import annotations

import json
from pathlib import Path

from evidence.compiler import compile_document_tree
from evidence.document_relation import RelationPredicate
from evidence.relation_builder import _linked_receipts_from_tree_value, build_relations
from evidence.relation_resolver import ManualRelationReview, ManualRelationReviews


def _write_document(
    corpus_root: Path,
    *,
    receipt_no: str,
    report_name: str,
    is_correction: bool,
    body: str,
) -> dict[str, object]:
    relative_directory = Path("raw") / "exchange" / "Acme" / receipt_no
    directory = corpus_root / relative_directory
    directory.mkdir(parents=True)
    (directory / f"{receipt_no}.xml").write_text(
        f"<DOCUMENT><BODY>{body}</BODY></DOCUMENT>",
        encoding="utf-8",
    )
    return {
        "doc_id": f"exchange_{receipt_no}",
        "corp_code": "00000001",
        "doc_group": "exchange",
        "doc_subtype": "단일판매공급계약체결",
        "report_nm": report_name,
        "is_correction": is_correction,
        "rcept_no": receipt_no,
        "rcept_dt": receipt_no[:8],
        "flr_nm": "Acme",
        "base_year": None,
        "base_month": None,
        "file_path": relative_directory.as_posix(),
        "file_format": "xml",
        "n_files": 1,
    }


def test_build_relations_applies_manual_review_and_writes_complete_snapshot(
    tmp_path: Path,
) -> None:
    corpus_root = tmp_path / "corpus"
    first = _write_document(
        corpus_root,
        receipt_no="20240101000001",
        report_name="단일판매ㆍ공급계약체결",
        is_correction=False,
        body="<P>Contract A</P>",
    )
    selected = _write_document(
        corpus_root,
        receipt_no="20240101000002",
        report_name="단일판매ㆍ공급계약체결",
        is_correction=False,
        body="<P>Contract B</P>",
    )
    source = _write_document(
        corpus_root,
        receipt_no="20240201000003",
        report_name="[기재정정]단일판매ㆍ공급계약체결",
        is_correction=True,
        body=(
            "<CORRECTION><P>공시서류제출일 : 2024-01-01</P></CORRECTION><P>Contract B corrected</P>"
        ),
    )
    (corpus_root / "manifest.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in (first, selected, source)),
        encoding="utf-8",
    )
    reviews = ManualRelationReviews(
        (
            ManualRelationReview(
                source_doc_id=str(source["doc_id"]),
                predicate=RelationPredicate.REVISES,
                candidate_doc_ids=(str(first["doc_id"]), str(selected["doc_id"])),
                selected_target_doc_id=str(selected["doc_id"]),
                rationale="The correction-before state matches Contract B.",
            ),
        )
    )

    report = build_relations(
        corpus_root,
        tmp_path / "output",
        workers=1,
        progress_every=0,
        manual_reviews=reviews,
    )

    relation_rows = [json.loads(line) for line in report.relations_path.read_text().splitlines()]
    assert report.documents_scanned == 3
    assert report.relation_sources == 1
    assert report.documents_compiled_with_grains == 3
    assert report.relations == 1
    assert report.unresolved == 0
    assert relation_rows == [
        {
            "source_doc_id": source["doc_id"],
            "source_grain_ids": relation_rows[0]["source_grain_ids"],
            "predicate": "revises",
            "target_doc_id": selected["doc_id"],
            "target_grain_ids": relation_rows[0]["target_grain_ids"],
        }
    ]
    assert report.unresolved_path.read_text(encoding="utf-8") == ""


def test_build_relations_is_deterministic_for_same_inputs(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    target = _write_document(
        corpus_root,
        receipt_no="20240101000001",
        report_name="단일판매ㆍ공급계약체결",
        is_correction=False,
        body="<P>Contract A</P>",
    )
    source = _write_document(
        corpus_root,
        receipt_no="20240201000003",
        report_name="[기재정정]단일판매ㆍ공급계약체결",
        is_correction=True,
        body="<CORRECTION><P>공시서류제출일 : 2024-01-01</P></CORRECTION>",
    )
    (corpus_root / "manifest.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in (target, source)),
        encoding="utf-8",
    )

    first = build_relations(
        corpus_root,
        tmp_path / "first",
        workers=1,
        progress_every=0,
        manual_reviews=ManualRelationReviews(),
    )
    second = build_relations(
        corpus_root,
        tmp_path / "second",
        workers=1,
        progress_every=0,
        manual_reviews=ManualRelationReviews(),
    )

    assert first.relations_path.read_bytes() == second.relations_path.read_bytes()
    assert first.unresolved_path.read_bytes() == second.unresolved_path.read_bytes()


def test_db_json_value_scan_finds_option_receipt_without_full_tree_validation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "20260619000667_viewer.html"
    source.write_text(
        '<SELECT><OPTION VALUE="rcpNo=20260324000835">prior</OPTION></SELECT>',
        encoding="utf-8",
    )
    tree = compile_document_tree(
        source,
        doc_id="periodic_20260619000667",
        corpus_root=tmp_path,
    )

    anchors = _linked_receipts_from_tree_value(tree.model_dump(mode="json"))

    assert [anchor.receipt_no for anchor in anchors] == ["20260324000835"]

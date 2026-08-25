from __future__ import annotations

import json
from pathlib import Path

from evidence.compiler import compile_document_tree
from evidence.document_grain import DocumentGrain, GrainKind
from evidence.document_tree import DocumentTree
from evidence.grain_compiler import compile_document_grains
from evidence.validate_grains import (
    validate_corpus_grains,
    validate_document_grain_set,
)

FIXTURE_BODY = (
    '<SECTION-1><TITLE ATOC="Y" ATOCID="7" AASSOCNOTE="D-1" '
    'ENG="Finance">Finance</TITLE>'
    "<P>Operating profit increased.</P>"
    "<TABLE><THEAD><TR><TH></TH><TH>Amount</TH></TR></THEAD><TBODY><TR>"
    '<TD ROWSPAN="2"></TD><TD COLSPAN="2" AUNIT="AMOUNT" '
    'AUNITVALUE="100">100</TD></TR></TBODY></TABLE>'
    '<A HREF="https://example.test/report">Related report</A>'
    '<IMG SRC="chart.png" AFILE="chart.png" />'
    "</SECTION-1>"
)


def _compile_fixture(tmp_path: Path) -> tuple[DocumentTree, tuple[DocumentGrain, ...]]:
    receipt_no = "20240101000001"
    directory = tmp_path / "raw" / "periodic" / "Acme" / receipt_no
    directory.mkdir(parents=True)
    source = directory / f"{receipt_no}.xml"
    source.write_text(
        f"<DOCUMENT><BODY>{FIXTURE_BODY}</BODY></DOCUMENT>",
        encoding="utf-8",
    )
    tree = compile_document_tree(
        directory,
        doc_id=f"periodic_{receipt_no}",
        corpus_root=tmp_path,
    )
    return tree, compile_document_grains(tree, max_estimated_tokens=200)


def test_validator_accepts_complete_semantic_grains(tmp_path: Path) -> None:
    tree, grains = _compile_fixture(tmp_path)

    failures = validate_document_grain_set(
        tree,
        grains,
        corpus_root=tmp_path,
        max_estimated_tokens=200,
    )

    assert failures == ()


def test_grains_do_not_copy_source_attributes(tmp_path: Path) -> None:
    tree, grains = _compile_fixture(tmp_path)

    failures = validate_document_grain_set(
        tree,
        grains,
        corpus_root=tmp_path,
        max_estimated_tokens=200,
    )

    assert failures == ()
    assert all(not hasattr(grain.context, "attributes") for grain in grains)


def test_validator_rejects_lost_empty_table_cell(tmp_path: Path) -> None:
    tree, grains = _compile_fixture(tmp_path)
    table = next(
        grain
        for grain in grains
        if grain.kind == GrainKind.TABLE and "c1[rowspan=2]=∅" in grain.core_text
    )
    replacement = table.model_copy(
        update={
            "core_text": table.core_text.replace("c1[rowspan=2]=∅", "c1[rowspan=2]=missing"),
            "rendered_text": table.rendered_text.replace(
                "c1[rowspan=2]=∅", "c1[rowspan=2]=missing"
            ),
        }
    )
    tampered = tuple(replacement if grain is table else grain for grain in grains)

    failures = validate_document_grain_set(
        tree,
        tampered,
        corpus_root=tmp_path,
        max_estimated_tokens=200,
    )

    assert any("empty table cell marker missing" in failure for failure in failures)


def test_validator_accepts_packed_row_ending_in_empty_cell(tmp_path: Path) -> None:
    receipt_no = "20240101000002"
    directory = tmp_path / "raw" / "periodic" / "Acme" / receipt_no
    directory.mkdir(parents=True)
    source = directory / f"{receipt_no}.xml"
    source.write_text(
        "<DOCUMENT><BODY><TABLE><TBODY>"
        "<TR><TD>first</TD><TD></TD></TR>"
        "<TR><TD>second</TD><TD>value</TD></TR>"
        "</TBODY></TABLE></BODY></DOCUMENT>",
        encoding="utf-8",
    )
    tree = compile_document_tree(
        directory,
        doc_id=f"periodic_{receipt_no}",
        corpus_root=tmp_path,
    )
    grains = compile_document_grains(tree, max_estimated_tokens=200)

    failures = validate_document_grain_set(
        tree,
        grains,
        corpus_root=tmp_path,
        max_estimated_tokens=200,
    )

    assert "c2=∅\nr2:" in grains[0].core_text
    assert failures == ()


def test_validator_ignores_empty_heading_with_attribute_only_label(tmp_path: Path) -> None:
    receipt_no = "20240101000003"
    directory = tmp_path / "raw" / "periodic" / "Acme" / receipt_no
    directory.mkdir(parents=True)
    source = directory / f"{receipt_no}.xml"
    source.write_text(
        '<DOCUMENT><BODY><TABLE-GROUP><TITLE ENG="English only"></TITLE>'
        "<TABLE><TR><TD>value</TD></TR></TABLE></TABLE-GROUP></BODY></DOCUMENT>",
        encoding="utf-8",
    )
    tree = compile_document_tree(
        directory,
        doc_id=f"periodic_{receipt_no}",
        corpus_root=tmp_path,
    )
    grains = compile_document_grains(tree, max_estimated_tokens=200)

    failures = validate_document_grain_set(
        tree,
        grains,
        corpus_root=tmp_path,
        max_estimated_tokens=200,
    )

    assert failures == ()


def test_validator_accepts_integrated_table_metadata_and_empty_layout(
    tmp_path: Path,
) -> None:
    receipt_no = "20240101000004"
    directory = tmp_path / "raw" / "periodic" / "Acme" / receipt_no
    directory.mkdir(parents=True)
    source = directory / f"{receipt_no}.xml"
    source.write_text(
        "<DOCUMENT><BODY>"
        '<TABLE BORDER="0"><TR><TD></TD></TR></TABLE>'
        '<TABLE BORDER="0"><TR><TD>Balance sheet</TD></TR>'
        "<TR><TD>(단위 : 백만원)</TD></TR></TABLE>"
        "<TABLE><THEAD><TR><TH>Item(*)</TH><TH>Amount</TH></TR></THEAD>"
        "<TR><TD>Assets</TD><TD>100</TD></TR></TABLE>"
        "<TABLE><TR><TD>(*) Includes subsidiaries.</TD></TR></TABLE>"
        "<TABLE><THEAD><TR><TH>Item(*)</TH><TH>Prior</TH></TR></THEAD>"
        "<TR><TD>Assets</TD><TD>90</TD></TR></TABLE>"
        "<P>※ Prior includes provisional amounts.</P>"
        "</BODY></DOCUMENT>",
        encoding="utf-8",
    )
    tree = compile_document_tree(
        directory,
        doc_id=f"periodic_{receipt_no}",
        corpus_root=tmp_path,
    )
    grains = compile_document_grains(tree, max_estimated_tokens=100)

    failures = validate_document_grain_set(
        tree,
        grains,
        corpus_root=tmp_path,
        max_estimated_tokens=100,
    )

    assert failures == ()
    assert all(grain.context.notes for grain in grains)
    assert all(grain.estimated_tokens <= 100 for grain in grains)


def test_corpus_validator_uses_worker_pool_without_database(tmp_path: Path) -> None:
    manifest_rows: list[dict[str, object]] = []
    for index in range(2):
        receipt_no = f"2024010100000{index + 1}"
        relative = f"raw/periodic/Acme/{receipt_no}"
        directory = tmp_path / relative
        directory.mkdir(parents=True)
        (directory / f"{receipt_no}.xml").write_text(
            "<DOCUMENT><BODY><P>Complete text.</P></BODY></DOCUMENT>",
            encoding="utf-8",
        )
        manifest_rows.append(
            {
                "doc_id": f"periodic_{receipt_no}",
                "corp_code": "001",
                "doc_group": "periodic",
                "doc_subtype": "annual",
                "report_nm": "Annual report",
                "is_correction": False,
                "rcept_no": receipt_no,
                "rcept_dt": "20240101",
                "flr_nm": "Acme",
                "base_year": 2023,
                "base_month": 12,
                "file_path": relative,
                "file_format": "xml",
                "n_files": 1,
            }
        )
    (tmp_path / "manifest.jsonl").write_text(
        "".join(f"{json.dumps(row)}\n" for row in manifest_rows),
        encoding="utf-8",
    )

    report = validate_corpus_grains(
        tmp_path,
        workers=2,
        progress_every=0,
        max_estimated_tokens=200,
    )

    assert report.passed
    assert report.checked_documents == 2
    assert report.compiled_grains == 2
    assert report.average_estimated_tokens > 0
    assert report.estimated_token_p50 > 0
    assert report.estimated_token_p90 >= report.estimated_token_p50
    assert report.estimated_token_p99 >= report.estimated_token_p90
    assert sum(report.token_bucket_counts.values()) == report.compiled_grains
    assert sum(report.grain_kind_counts.values()) == report.compiled_grains

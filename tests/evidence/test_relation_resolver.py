from pathlib import Path

from evidence.compiler import compile_document_tree
from evidence.document_grain import DocumentGrain
from evidence.document_relation import RelationPredicate, validate_relation_grains
from evidence.document_tree import DocumentTree, NodeKind, walk_nodes
from evidence.grain_compiler import compile_document_grains
from evidence.relation_resolver import (
    DocumentRelationResolver,
    ManualRelationReview,
    ManualRelationReviews,
    RelationCatalog,
    RelationDocument,
    RelationResolutionContext,
    UnresolvedReason,
    grain_ids_overlapping_range,
)


def compile_fixture(
    tmp_path: Path,
    receipt_no: str,
    body: str,
) -> tuple[DocumentTree, tuple[DocumentGrain, ...]]:
    directory = tmp_path / receipt_no
    directory.mkdir()
    source = directory / f"{receipt_no}.xml"
    source.write_text(f"<DOCUMENT><BODY>{body}</BODY></DOCUMENT>", encoding="utf-8")
    tree = compile_document_tree(
        source,
        doc_id=f"exchange_{receipt_no}",
        corpus_root=tmp_path,
    )
    return tree, compile_document_grains(tree)


def document(
    receipt_no: str,
    *,
    report_name: str,
    doc_subtype: str,
    is_correction: bool = False,
) -> RelationDocument:
    return RelationDocument(
        doc_id=f"exchange_{receipt_no}",
        receipt_no=receipt_no,
        corp_code="001",
        doc_group="exchange",
        doc_subtype=doc_subtype,
        report_name=report_name,
        is_correction=is_correction,
        filer_name="Acme",
    )


def context(
    source_document: RelationDocument,
    source_tree: DocumentTree,
    source_grains: tuple[DocumentGrain, ...],
    documents: tuple[RelationDocument, ...],
    grains_by_doc_id: dict[str, tuple[DocumentGrain, ...]],
) -> RelationResolutionContext:
    return RelationResolutionContext(
        source_document=source_document,
        source_tree=source_tree,
        source_grains=source_grains,
        catalog=RelationCatalog(documents),
        grains_by_doc_id=grains_by_doc_id,
    )


def test_catalog_document_accepts_loader_and_raw_manifest_field_names() -> None:
    loader = RelationDocument.from_mapping(
        {
            "doc_id": "exchange_20240101000001",
            "receipt_no": "20240101000001",
            "corp_code": "001",
            "doc_group": "exchange",
            "doc_subtype": "신규시설투자등",
            "report_name": "신규시설투자등",
            "is_correction": False,
            "filer_name": "Acme",
            "base_year": None,
            "base_month": None,
        }
    )
    raw = RelationDocument.from_mapping(
        {
            "doc_id": "exchange_20240101000001",
            "rcept_no": "20240101000001",
            "corp_code": "001",
            "doc_group": "exchange",
            "doc_subtype": "신규시설투자등",
            "report_nm": "신규시설투자등",
            "is_correction": False,
            "flr_nm": "Acme",
        }
    )

    assert loader == raw


def test_catalog_resolves_krx_link_receipt_alias_only_to_exchange_document() -> None:
    target = document(
        "20241015800258",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    catalog = RelationCatalog((target,))

    assert catalog.by_linked_receipt_no("20241015000258") == target


def test_receipt_link_resolves_document_and_exact_source_grain(tmp_path: Path) -> None:
    target_document = document(
        "20231231000001",
        report_name="시설투자",
        doc_subtype="신규시설투자등",
    )
    source_document = document(
        "20240101000001",
        report_name="주요경영사항",
        doc_subtype="투자판단관련주요경영사항",
    )
    target_tree, target_grains = compile_fixture(
        tmp_path,
        target_document.receipt_no,
        "<P>시설투자</P>",
    )
    source_tree, source_grains = compile_fixture(
        tmp_path,
        source_document.receipt_no,
        ('<P>body</P><A HREF="https://kind.example/view?rcpno=20231231000001">시설투자</A>'),
    )

    relations = DocumentRelationResolver().resolve(
        context(
            source_document,
            source_tree,
            source_grains,
            (source_document, target_document),
            {
                source_document.doc_id: source_grains,
                target_document.doc_id: target_grains,
            },
        )
    )

    assert len(relations) == 1
    relation = relations[0]
    assert relation.predicate == RelationPredicate.REFERENCES
    assert relation.target_doc_id == target_document.doc_id
    assert relation.source_grain_ids
    assert relation.target_grain_ids == ()
    validate_relation_grains(
        relation,
        grains_by_id={grain.grain_id: grain for grain in (*source_grains, *target_grains)},
    )


def test_external_or_unknown_receipt_link_is_not_an_edge(tmp_path: Path) -> None:
    source_document = document(
        "20240101000001",
        report_name="주요경영사항",
        doc_subtype="투자판단관련주요경영사항",
    )
    source_tree, source_grains = compile_fixture(
        tmp_path,
        source_document.receipt_no,
        '<A HREF="https://kind.example/view?acptno=19990101000001">old filing</A>',
    )

    relations = DocumentRelationResolver().resolve(
        context(
            source_document,
            source_tree,
            source_grains,
            (source_document,),
            {source_document.doc_id: source_grains},
        )
    )

    assert relations == ()


def test_rcpno_wins_when_both_receipt_parameters_are_present(tmp_path: Path) -> None:
    target_document = document(
        "20231231000001",
        report_name="시설투자",
        doc_subtype="신규시설투자등",
    )
    source_document = document(
        "20240101000001",
        report_name="주요경영사항",
        doc_subtype="투자판단관련주요경영사항",
    )
    source_tree, source_grains = compile_fixture(
        tmp_path,
        source_document.receipt_no,
        (
            '<A HREF="https://kind.example/view?acptno=19990101000001'
            '&amp;rcpno=20231231000001">시설투자</A>'
        ),
    )

    relations = DocumentRelationResolver().resolve(
        context(
            source_document,
            source_tree,
            source_grains,
            (source_document, target_document),
            {},
        )
    )

    assert len(relations) == 1
    assert relations[0].target_doc_id == target_document.doc_id


def test_termination_link_adds_terminates_without_losing_reference(tmp_path: Path) -> None:
    target_document = document(
        "20231231000001",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    source_document = document(
        "20240101000001",
        report_name="단일판매ㆍ공급계약해지",
        doc_subtype="단일판매공급계약해지",
    )
    target_tree, target_grains = compile_fixture(
        tmp_path,
        target_document.receipt_no,
        "<P>단일판매ㆍ공급계약체결</P>",
    )
    source_tree, source_grains = compile_fixture(
        tmp_path,
        source_document.receipt_no,
        (
            '<A HREF="https://kind.example/view?acptno=20231231000001">'
            "2023-12-31 단일판매ㆍ공급계약체결</A>"
        ),
    )

    relations = DocumentRelationResolver().resolve(
        context(
            source_document,
            source_tree,
            source_grains,
            (source_document, target_document),
            {target_document.doc_id: target_grains},
        )
    )

    assert {relation.predicate for relation in relations} == {
        RelationPredicate.REFERENCES,
        RelationPredicate.TERMINATES,
    }
    assert all(relation.source_grain_ids for relation in relations)
    assert all(relation.target_grain_ids == () for relation in relations)


def test_history_links_reference_all_but_revise_only_latest_prior(tmp_path: Path) -> None:
    original = document(
        "20240101000001",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    prior_correction = document(
        "20240201000002",
        report_name="[기재정정]단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
        is_correction=True,
    )
    source = document(
        "20240301000003",
        report_name="[기재정정]단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
        is_correction=True,
    )
    source_tree, source_grains = compile_fixture(
        tmp_path,
        source.receipt_no,
        (
            '<A HREF="?rcpno=20240101000001">original</A>'
            '<A HREF="?rcpno=20240201000002">prior correction</A>'
        ),
    )

    relations = DocumentRelationResolver().resolve(
        context(
            source,
            source_tree,
            source_grains,
            (source, original, prior_correction),
            {},
        )
    )

    references = {
        relation.target_doc_id
        for relation in relations
        if relation.predicate == RelationPredicate.REFERENCES
    }
    revises = [
        relation for relation in relations if relation.predicate == RelationPredicate.REVISES
    ]
    assert references == {original.doc_id, prior_correction.doc_id}
    assert [relation.target_doc_id for relation in revises] == [prior_correction.doc_id]


def test_viewer_option_receipt_history_resolves_latest_prior(tmp_path: Path) -> None:
    original = document(
        "20240101000001",
        report_name="사업보고서",
        doc_subtype="annual",
    )
    prior = document(
        "20240201000002",
        report_name="[기재정정]사업보고서",
        doc_subtype="annual",
        is_correction=True,
    )
    source = document(
        "20240301000003",
        report_name="[기재정정]사업보고서",
        doc_subtype="annual",
        is_correction=True,
    )
    source_tree, source_grains = compile_fixture(
        tmp_path,
        source.receipt_no,
        (
            '<SELECT><OPTION VALUE="rcpNo=20240101000001">original</OPTION>'
            '<OPTION VALUE="rcpNo=20240201000002">prior</OPTION></SELECT>'
        ),
    )

    relations = DocumentRelationResolver().resolve(
        context(source, source_tree, source_grains, (source, original, prior), {})
    )

    revises = [
        relation for relation in relations if relation.predicate == RelationPredicate.REVISES
    ]
    assert [relation.target_doc_id for relation in revises] == [prior.doc_id]
    assert revises[0].source_grain_ids


def test_correction_link_adds_revises_and_skips_history_fallback(tmp_path: Path) -> None:
    target_document = document(
        "20231231000001",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    unrelated_prior = document(
        "20230101000001",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    source_document = document(
        "20240101000001",
        report_name="[기재정정]단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
        is_correction=True,
    )
    source_tree, source_grains = compile_fixture(
        tmp_path,
        source_document.receipt_no,
        ('<A HREF="https://kind.example/view?rcpno=20231231000001">단일판매ㆍ공급계약체결</A>'),
    )

    relations = DocumentRelationResolver().resolve(
        context(
            source_document,
            source_tree,
            source_grains,
            (source_document, target_document, unrelated_prior),
            {},
        )
    )

    assert {relation.predicate for relation in relations} == {
        RelationPredicate.REFERENCES,
        RelationPredicate.REVISES,
    }
    assert {relation.target_doc_id for relation in relations} == {target_document.doc_id}


def test_unique_correction_history_fallback_uses_correction_grain(tmp_path: Path) -> None:
    target_document = document(
        "20231231000001",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    source_document = document(
        "20240101000001",
        report_name="[기재정정]단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
        is_correction=True,
    )
    source_tree, source_grains = compile_fixture(
        tmp_path,
        source_document.receipt_no,
        "<CORRECTION><P>정정신고 내용</P></CORRECTION><P>changed body</P>",
    )

    relations = DocumentRelationResolver().resolve(
        context(
            source_document,
            source_tree,
            source_grains,
            (source_document, target_document),
            {},
        )
    )

    assert len(relations) == 1
    assert relations[0].predicate == RelationPredicate.REVISES
    assert relations[0].target_doc_id == target_document.doc_id
    assert relations[0].source_grain_ids
    assert relations[0].target_grain_ids == ()


def test_ambiguous_correction_history_does_not_guess_a_target(tmp_path: Path) -> None:
    source_document = document(
        "20240101000001",
        report_name="[기재정정]단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
        is_correction=True,
    )
    first = document(
        "20230101000001",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    second = document(
        "20230201000001",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    source_tree, source_grains = compile_fixture(
        tmp_path,
        source_document.receipt_no,
        "<CORRECTION><P>정정신고 내용</P></CORRECTION>",
    )

    relations = DocumentRelationResolver().resolve(
        context(
            source_document,
            source_tree,
            source_grains,
            (source_document, first, second),
            {},
        )
    )

    assert relations == ()


def test_original_filing_date_narrows_same_name_candidates(tmp_path: Path) -> None:
    source_document = document(
        "20250101000001",
        report_name="[기재정정]단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
        is_correction=True,
    )
    wrong_date = document(
        "20241014800001",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    right_date = document(
        "20241015800001",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    source_tree, source_grains = compile_fixture(
        tmp_path,
        source_document.receipt_no,
        (
            "<CORRECTION><P>2. 정정관련 공시서류제출일 : "
            "2024년 10월 15일</P></CORRECTION><P>changed body</P>"
        ),
    )

    result = DocumentRelationResolver(manual_reviews=ManualRelationReviews()).resolve_detailed(
        context(
            source_document,
            source_tree,
            source_grains,
            (source_document, wrong_date, right_date),
            {},
        )
    )

    assert len(result.relations) == 1
    assert result.relations[0].target_doc_id == right_date.doc_id
    assert result.unresolved == ()


def test_original_date_without_an_in_corpus_match_stays_unresolved(tmp_path: Path) -> None:
    source_document = document(
        "20250101000001",
        report_name="[기재정정]단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
        is_correction=True,
    )
    wrong_date = document(
        "20241014800001",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    source_tree, source_grains = compile_fixture(
        tmp_path,
        source_document.receipt_no,
        (
            "<CORRECTION><P>2. 정정관련 공시서류제출일 : "
            "2024년 10월 15일</P></CORRECTION><P>changed body</P>"
        ),
    )

    result = DocumentRelationResolver().resolve_detailed(
        context(
            source_document,
            source_tree,
            source_grains,
            (source_document, wrong_date),
            {},
        )
    )

    assert result.relations == ()
    assert result.unresolved[0].reason == UnresolvedReason.NO_IN_CORPUS_CANDIDATE
    assert result.unresolved[0].candidate_doc_ids == (wrong_date.doc_id,)


def test_grain_content_never_selects_or_orders_a_target(tmp_path: Path) -> None:
    source_document = document(
        "20251217800853",
        report_name="[기재정정]단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
        is_correction=True,
    )
    matching = document(
        "20241015800258",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    conflicting = document(
        "20241015800261",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    matching_tree, matching_grains = compile_fixture(
        tmp_path,
        matching.receipt_no,
        "<TABLE><TR><TD>Ford Motor Company</TD><TD>75GWh</TD></TR></TABLE>",
    )
    conflicting_tree, conflicting_grains = compile_fixture(
        tmp_path,
        conflicting.receipt_no,
        "<TABLE><TR><TD>Ford Motor Company</TD><TD>34GWh</TD></TR></TABLE>",
    )
    source_tree, source_grains = compile_fixture(
        tmp_path,
        source_document.receipt_no,
        (
            "<CORRECTION><P>2. 정정관련 공시서류제출일 : "
            "2024년 10월 15일</P></CORRECTION>"
            "<TABLE><TR><TD>Ford Motor Company</TD><TD>75GWh</TD></TR></TABLE>"
        ),
    )

    result = DocumentRelationResolver(manual_reviews=ManualRelationReviews()).resolve_detailed(
        context(
            source_document,
            source_tree,
            source_grains,
            (source_document, matching, conflicting),
            {
                matching.doc_id: matching_grains,
                conflicting.doc_id: conflicting_grains,
            },
        )
    )

    assert result.relations == ()
    assert result.unresolved[0].reason == UnresolvedReason.AMBIGUOUS_CANDIDATES
    assert result.unresolved[0].candidate_doc_ids == (conflicting.doc_id, matching.doc_id)


def test_manual_review_breaks_a_semantic_tie(tmp_path: Path) -> None:
    source_document = document(
        "20250101000001",
        report_name="[기재정정]단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
        is_correction=True,
    )
    first = document(
        "20241015800001",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    second = document(
        "20241015800002",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    first_tree, first_grains = compile_fixture(
        tmp_path,
        first.receipt_no,
        "<P>same contract content</P>",
    )
    second_tree, second_grains = compile_fixture(
        tmp_path,
        second.receipt_no,
        "<P>same contract content</P>",
    )
    source_tree, source_grains = compile_fixture(
        tmp_path,
        source_document.receipt_no,
        (
            "<CORRECTION><P>공시서류제출일 : 2024년 10월 15일</P></CORRECTION>"
            "<P>same contract content</P>"
        ),
    )
    reviews = ManualRelationReviews(
        (
            ManualRelationReview(
                source_doc_id=source_document.doc_id,
                predicate=RelationPredicate.REVISES,
                candidate_doc_ids=(first.doc_id, second.doc_id),
                selected_target_doc_id=second.doc_id,
                rationale="The correction-before state matches the second filing.",
            ),
        )
    )

    result = DocumentRelationResolver(manual_reviews=reviews).resolve_detailed(
        context(
            source_document,
            source_tree,
            source_grains,
            (source_document, first, second),
            {first.doc_id: first_grains, second.doc_id: second_grains},
        )
    )

    assert result.relations[0].target_doc_id == second.doc_id
    assert result.unresolved == ()


def test_manual_review_is_ignored_when_candidate_set_changed(tmp_path: Path) -> None:
    source_document = document(
        "20250101000001",
        report_name="[기재정정]단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
        is_correction=True,
    )
    first = document(
        "20241015800001",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    second = document(
        "20241015800002",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    third = document(
        "20241015800003",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    source_tree, source_grains = compile_fixture(
        tmp_path,
        source_document.receipt_no,
        "<CORRECTION><P>공시서류제출일 : 2024년 10월 15일</P></CORRECTION>",
    )
    reviews = ManualRelationReviews(
        (
            ManualRelationReview(
                source_doc_id=source_document.doc_id,
                predicate=RelationPredicate.REVISES,
                candidate_doc_ids=(first.doc_id, second.doc_id),
                selected_target_doc_id=second.doc_id,
                rationale="Reviewed before the third candidate appeared.",
            ),
        )
    )

    result = DocumentRelationResolver(manual_reviews=reviews).resolve_detailed(
        context(
            source_document,
            source_tree,
            source_grains,
            (source_document, first, second, third),
            {},
        )
    )

    assert result.relations == ()
    assert result.unresolved[0].reason == UnresolvedReason.AMBIGUOUS_CANDIDATES


def test_manual_review_can_abstain_when_no_candidate_matches(tmp_path: Path) -> None:
    review_path = tmp_path / "reviews.jsonl"
    review_path.write_text(
        '{"source_doc_id":"exchange_source","predicate":"revises",'
        '"candidate_doc_ids":["exchange_first","exchange_second"],'
        '"selected_target_doc_id":null,'
        '"rationale":"The correct predecessor is not in the corpus."}\n',
        encoding="utf-8",
    )
    reviews = ManualRelationReviews.from_jsonl(review_path)

    assert (
        reviews.choose(
            "exchange_source",
            RelationPredicate.REVISES,
            ("exchange_first", "exchange_second"),
        )
        is None
    )


def test_manual_review_abstention_is_a_reviewed_no_match_outcome(
    tmp_path: Path,
) -> None:
    source = document(
        "20250101000003",
        report_name="[기재정정]단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
        is_correction=True,
    )
    first = document(
        "20241015800001",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    second = document(
        "20241015800002",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    source_tree, source_grains = compile_fixture(
        tmp_path,
        source.receipt_no,
        "<CORRECTION><P>공시서류제출일 : 2024-10-15</P></CORRECTION>",
    )
    reviews = ManualRelationReviews(
        (
            ManualRelationReview(
                source_doc_id=source.doc_id,
                predicate=RelationPredicate.REVISES,
                candidate_doc_ids=(first.doc_id, second.doc_id),
                selected_target_doc_id=None,
                rationale="No candidate is the corrected filing.",
            ),
        )
    )

    result = DocumentRelationResolver(manual_reviews=reviews).resolve_detailed(
        context(source, source_tree, source_grains, (source, first, second), {})
    )

    assert result.relations == ()
    assert result.unresolved[0].reason == UnresolvedReason.REVIEWED_NO_MATCH


def test_prior_correction_with_same_root_date_is_a_series_candidate(
    tmp_path: Path,
) -> None:
    source_document = document(
        "20241011000053",
        report_name="[기재정정3]단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
        is_correction=True,
    )
    original = document(
        "20241002000155",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    prior_correction = document(
        "20241004000001",
        report_name="[기재정정2]단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
        is_correction=True,
    )
    original_tree, original_grains = compile_fixture(
        tmp_path,
        original.receipt_no,
        "<P>same body</P>",
    )
    prior_tree, prior_grains = compile_fixture(
        tmp_path,
        prior_correction.receipt_no,
        ("<CORRECTION><P>최초제출일 : 2024년 10월 2일</P></CORRECTION><P>same body</P>"),
    )
    source_tree, source_grains = compile_fixture(
        tmp_path,
        source_document.receipt_no,
        ("<CORRECTION><P>최초제출일 : 2024년 10월 2일</P></CORRECTION><P>same body</P>"),
    )
    result = DocumentRelationResolver(manual_reviews=ManualRelationReviews()).resolve_detailed(
        context(
            source_document,
            source_tree,
            source_grains,
            (source_document, original, prior_correction),
            {
                original.doc_id: original_grains,
                prior_correction.doc_id: prior_grains,
            },
        )
    )

    assert result.relations[0].target_doc_id == prior_correction.doc_id
    assert result.unresolved == ()


def test_rendered_table_markers_do_not_hide_candidate_root_date(
    tmp_path: Path,
) -> None:
    source_document = document(
        "20241011000053",
        report_name="[기재정정3]단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
        is_correction=True,
    )
    original = document(
        "20241002000155",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    prior_correction = document(
        "20241004000001",
        report_name="[기재정정2]단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
        is_correction=True,
    )
    original_tree, original_grains = compile_fixture(
        tmp_path,
        original.receipt_no,
        "<P>same body</P>",
    )
    prior_tree, prior_grains = compile_fixture(
        tmp_path,
        prior_correction.receipt_no,
        (
            "<TABLE><TR><TD>정정관련 공시서류제출일</TD>"
            '<TD COLSPAN="2">2024-10-02</TD></TR></TABLE><P>same body</P>'
        ),
    )
    source_tree, source_grains = compile_fixture(
        tmp_path,
        source_document.receipt_no,
        "<P>최초제출일 : 2024-10-02</P><P>same body</P>",
    )

    result = DocumentRelationResolver(manual_reviews=ManualRelationReviews()).resolve_detailed(
        context(
            source_document,
            source_tree,
            source_grains,
            (source_document, original, prior_correction),
            {
                original.doc_id: original_grains,
                prior_correction.doc_id: prior_grains,
            },
        )
    )

    assert result.relations[0].target_doc_id == prior_correction.doc_id
    assert result.unresolved == ()


def test_multiple_candidates_without_manual_review_are_reported_unresolved(
    tmp_path: Path,
) -> None:
    source_document = document(
        "20250101000001",
        report_name="[기재정정]단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
        is_correction=True,
    )
    first = document(
        "20241015800001",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    second = document(
        "20241015800002",
        report_name="단일판매ㆍ공급계약체결",
        doc_subtype="단일판매공급계약체결",
    )
    first_tree, first_grains = compile_fixture(
        tmp_path,
        first.receipt_no,
        "<P>same contract content</P>",
    )
    second_tree, second_grains = compile_fixture(
        tmp_path,
        second.receipt_no,
        "<P>same contract content</P>",
    )
    source_tree, source_grains = compile_fixture(
        tmp_path,
        source_document.receipt_no,
        (
            "<CORRECTION><P>공시서류제출일 : 2024년 10월 15일</P></CORRECTION>"
            "<P>same contract content</P>"
        ),
    )

    result = DocumentRelationResolver().resolve_detailed(
        context(
            source_document,
            source_tree,
            source_grains,
            (source_document, first, second),
            {first.doc_id: first_grains, second.doc_id: second_grains},
        )
    )

    assert result.relations == ()
    assert len(result.unresolved) == 1
    assert result.unresolved[0].reason == UnresolvedReason.AMBIGUOUS_CANDIDATES
    assert set(result.unresolved[0].candidate_doc_ids) == {first.doc_id, second.doc_id}


def test_source_range_does_not_bind_through_repeated_context(tmp_path: Path) -> None:
    tree, grains = compile_fixture(
        tmp_path,
        "20240101000001",
        ('<SECTION-1><TITLE ATOC="Y">Related disclosure</TITLE><P>body</P></SECTION-1>'),
    )
    heading = next(
        node
        for artifact in tree.artifacts
        for node in walk_nodes(artifact.root)
        if node.kind == NodeKind.HEADING
    )
    assert any(heading.source in grain.source.context_ranges for grain in grains)

    assert grain_ids_overlapping_range(heading.source, grains) == ()

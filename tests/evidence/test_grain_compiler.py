from __future__ import annotations

from pathlib import Path

from evidence.compiler import compile_document_tree
from evidence.document_grain import GrainKind
from evidence.document_tree import DocumentTree
from evidence.grain_compiler import compile_document_grains


def compile_fixture(tmp_path: Path, body: str) -> tuple[DocumentTree, bytes]:
    receipt_no = "20240101000001"
    source_directory = tmp_path / "raw" / "periodic" / "Acme" / receipt_no
    source_directory.mkdir(parents=True)
    source = source_directory / f"{receipt_no}.xml"
    source.write_text(f"<DOCUMENT><BODY>{body}</BODY></DOCUMENT>", encoding="utf-8")
    return (
        compile_document_tree(
            source,
            doc_id=f"periodic_{receipt_no}",
            corpus_root=tmp_path,
        ),
        source.read_bytes(),
    )


def test_grain_keeps_nested_heading_context_and_exact_source_address(tmp_path: Path) -> None:
    tree, source_bytes = compile_fixture(
        tmp_path,
        (
            '<SECTION-1><TITLE ATOC="Y">III. Finance</TITLE>'
            '<SECTION-2><TITLE ATOC="Y">3. Notes</TITLE>'
            '<TABLE-GROUP><TITLE ATOC="Y">1. Company</TITLE>'
            "<P>Acme was founded in 2020.</P>"
            "</TABLE-GROUP></SECTION-2></SECTION-1>"
        ),
    )

    grain = next(grain for grain in compile_document_grains(tree) if "founded" in grain.core_text)

    assert grain.kind == GrainKind.PROSE
    assert grain.context.heading_path == (
        "III. Finance",
        "3. Notes",
        "1. Company",
    )
    assert grain.rendered_text.endswith(grain.core_text)
    assert len(grain.source.context_ranges) == 3
    for source_range in grain.source.core_ranges:
        assert source_bytes[source_range.start_byte : source_range.end_byte]


def test_table_slices_repeat_headers_without_duplicating_core_ranges(tmp_path: Path) -> None:
    rows = "".join(f"<TR><TD>asset-{index}</TD><TD>{index * 100}</TD></TR>" for index in range(12))
    tree, _ = compile_fixture(
        tmp_path,
        (
            '<SECTION-1><TITLE ATOC="Y">III. Finance</TITLE>'
            "<TABLE><THEAD><TR><TH>Asset</TH><TH>Amount</TH></TR></THEAD>"
            f"<TBODY>{rows}</TBODY></TABLE></SECTION-1>"
        ),
    )

    grains = tuple(
        grain
        for grain in compile_document_grains(tree, max_estimated_tokens=60)
        if grain.kind == GrainKind.TABLE
    )

    assert len(grains) > 1
    assert all(grain.context.table_headers == ("r1: c1=Asset | c2=Amount",) for grain in grains)
    assert all(
        "Table headers:\nr1: c1=Asset | c2=Amount" in grain.rendered_text for grain in grains
    )
    core_ranges = [
        (source_range.start_byte, source_range.end_byte)
        for grain in grains
        for source_range in grain.source.core_ranges
    ]
    assert len(core_ranges) == len(set(core_ranges)) == 12
    assert all(grain.source.context_ranges for grain in grains)


def test_adjacent_table_caption_and_unit_become_main_table_context(
    tmp_path: Path,
) -> None:
    tree, _ = compile_fixture(
        tmp_path,
        (
            '<SECTION-1><TITLE ATOC="Y">Sales</TITLE>'
            "<TABLE><TR><TD>[Regional sales]</TD></TR></TABLE>"
            "<P></P>"
            "<TABLE><TR><TD></TD><TD>(단위 : 백만원)</TD></TR></TABLE>"
            "<TABLE><THEAD><TR><TH>Region</TH><TH>Amount</TH></TR></THEAD>"
            "<TBODY><TR><TD>Seoul</TD><TD>100</TD></TR></TBODY></TABLE>"
            "</SECTION-1>"
        ),
    )

    table_grains = tuple(
        grain for grain in compile_document_grains(tree) if grain.kind == GrainKind.TABLE
    )

    assert len(table_grains) == 1
    grain = table_grains[0]
    assert grain.context.caption == "[Regional sales]"
    assert grain.context.unit == "(단위 : 백만원)"
    assert "Regional sales" not in grain.core_text
    assert "단위" not in grain.core_text
    assert "c1=Seoul | c2=100" in grain.core_text
    assert len(grain.source.context_ranges) == 6


def test_caption_and_unit_cells_in_one_row_become_context(tmp_path: Path) -> None:
    tree, _ = compile_fixture(
        tmp_path,
        (
            "<TABLE><TR><TD>[Research cost]</TD>"
            "<TD>(단위 : 백만원, %)</TD></TR></TABLE>"
            "<TABLE><TR><TD>Current year</TD><TD>100</TD></TR></TABLE>"
        ),
    )

    tables = tuple(
        grain for grain in compile_document_grains(tree) if grain.kind == GrainKind.TABLE
    )

    assert len(tables) == 1
    assert tables[0].context.caption == "[Research cost]"
    assert tables[0].context.unit == "(단위 : 백만원, %)"
    assert "Current year" in tables[0].core_text


def test_table_decoration_does_not_cross_meaningful_prose(tmp_path: Path) -> None:
    tree, _ = compile_fixture(
        tmp_path,
        (
            "<TABLE><TR><TD>(단위 : 백만원)</TD></TR></TABLE>"
            "<P>This paragraph breaks table adjacency.</P>"
            "<TABLE><TR><TD>Revenue</TD><TD>100</TD></TR></TABLE>"
        ),
    )

    grains = compile_document_grains(tree)
    tables = tuple(grain for grain in grains if grain.kind == GrainKind.TABLE)

    assert len(tables) == 2
    assert tables[0].core_text == "r1: c1=(단위 : 백만원)"
    assert tables[1].context.unit is None


def test_trailing_table_note_becomes_repeated_context(tmp_path: Path) -> None:
    tree, _ = compile_fixture(
        tmp_path,
        (
            "<TABLE><THEAD><TR><TH>Region</TH><TH>Amount</TH></TR></THEAD>"
            "<TBODY><TR><TD>Seoul</TD><TD>100</TD></TR></TBODY></TABLE>"
            "<P></P>"
            "<TABLE><TR><TD>※ Amounts are unaudited.</TD></TR></TABLE>"
        ),
    )

    tables = tuple(
        grain for grain in compile_document_grains(tree) if grain.kind == GrainKind.TABLE
    )

    assert len(tables) == 1
    assert tables[0].context.notes == ("※ Amounts are unaudited.",)
    assert "Amounts are unaudited" not in tables[0].core_text
    assert "Notes:\n※ Amounts are unaudited." in tables[0].rendered_text


def test_trailing_note_crosses_table_group_wrapper(tmp_path: Path) -> None:
    note = "※ This note explains the grouped table."
    tree, _ = compile_fixture(
        tmp_path,
        (
            "<TABLE-GROUP><TABLE><TR><TD>Revenue</TD><TD>100</TD></TR>"
            "</TABLE></TABLE-GROUP>"
            f"<TABLE><TR><TD>{note}</TD></TR></TABLE>"
        ),
    )

    tables = tuple(
        grain for grain in compile_document_grains(tree) if grain.kind == GrainKind.TABLE
    )

    assert len(tables) == 1
    assert tables[0].context.notes == (note,)


def test_trailing_note_paragraph_becomes_table_context(tmp_path: Path) -> None:
    note = "※ Production capacity uses actual available operating time."
    tree, _ = compile_fixture(
        tmp_path,
        (f"<TABLE><TR><TD>Steel</TD><TD>10,920</TD></TR></TABLE><P>{note}</P>"),
    )

    grains = compile_document_grains(tree)
    tables = tuple(grain for grain in grains if grain.kind == GrainKind.TABLE)

    assert len(tables) == 1
    assert tables[0].context.notes == (note,)
    assert note not in tables[0].core_text
    assert not any(note in grain.core_text for grain in grains)
    assert tables[0].source.context_ranges


def test_long_trailing_note_resplits_table_instead_of_becoming_standalone(
    tmp_path: Path,
) -> None:
    rows = "".join(f"<TR><TD>region-{index}</TD><TD>{index * 100}</TD></TR>" for index in range(10))
    note = "※ Amounts include internal transactions and provisional adjustments."
    tree, _ = compile_fixture(
        tmp_path,
        (
            "<TABLE><THEAD><TR><TH>Region</TH><TH>Amount</TH></TR></THEAD>"
            f"<TBODY>{rows}</TBODY></TABLE>"
            f"<TABLE><TR><TD>{note}</TD></TR></TABLE>"
        ),
    )

    tables = tuple(
        grain
        for grain in compile_document_grains(tree, max_estimated_tokens=45)
        if grain.kind == GrainKind.TABLE
    )

    assert len(tables) > 1
    assert all(grain.context.notes == (note,) for grain in tables)
    assert all(note not in grain.core_text for grain in tables)
    assert all(grain.estimated_tokens <= 45 for grain in tables)


def test_note_shaped_long_disclosure_remains_main_content(tmp_path: Path) -> None:
    disclosure = "(*) " + "substantive disclosure item " * 180
    tree, _ = compile_fixture(
        tmp_path,
        (
            "<TABLE><TR><TD>Revenue</TD><TD>100</TD></TR></TABLE>"
            f"<TABLE><TR><TD>{disclosure}</TD></TR></TABLE>"
        ),
    )

    tables = tuple(
        grain for grain in compile_document_grains(tree) if grain.kind == GrainKind.TABLE
    )

    assert all(not grain.context.notes for grain in tables)
    assert any("substantive disclosure item" in grain.core_text for grain in tables)


def test_footnote_between_split_tables_is_context_for_both(tmp_path: Path) -> None:
    note = "(*) Amount includes subsidiaries."
    tree, _ = compile_fixture(
        tmp_path,
        (
            "<TABLE><THEAD><TR><TH>Current(*)</TH></TR></THEAD>"
            "<TR><TD>100</TD></TR></TABLE>"
            f"<TABLE><TR><TD>{note}</TD></TR></TABLE>"
            "<TABLE><THEAD><TR><TH>Prior(*)</TH></TR></THEAD>"
            "<TR><TD>90</TD></TR></TABLE>"
        ),
    )

    tables = tuple(
        grain for grain in compile_document_grains(tree) if grain.kind == GrainKind.TABLE
    )

    assert len(tables) == 2
    assert all(grain.context.notes == (note,) for grain in tables)


def test_numbered_notes_attach_only_to_rows_with_matching_markers(
    tmp_path: Path,
) -> None:
    first_note = "(주1) Alpha amount includes subsidiaries."
    second_note = "(주2) Beta amount is provisional."
    tree, _ = compile_fixture(
        tmp_path,
        (
            "<TABLE><THEAD><TR><TH>Company</TH><TH>Amount</TH></TR></THEAD>"
            "<TBODY><TR><TD>Alpha(주1)</TD><TD>100</TD></TR>"
            "<TR><TD>Beta(주2)</TD><TD>200</TD></TR></TBODY></TABLE>"
            f"<TABLE><TR><TD>{first_note}</TD></TR></TABLE>"
            f"<TABLE><TR><TD>{second_note}</TD></TR></TABLE>"
        ),
    )

    tables = tuple(
        grain for grain in compile_document_grains(tree) if grain.kind == GrainKind.TABLE
    )
    alpha = next(grain for grain in tables if "Alpha" in grain.core_text)
    beta = next(grain for grain in tables if "Beta" in grain.core_text)

    assert alpha.context.notes == (first_note,)
    assert beta.context.notes == (second_note,)
    assert first_note not in beta.rendered_text
    assert second_note not in alpha.rendered_text
    assert alpha.source.context_ranges
    assert beta.source.context_ranges


def test_borderless_statement_title_date_and_unit_become_context(
    tmp_path: Path,
) -> None:
    tree, _ = compile_fixture(
        tmp_path,
        (
            '<TABLE BORDER="0"><TR><TD>Consolidated balance sheet</TD></TR>'
            "<TR><TD>As of 2024-12-31</TD></TR>"
            "<TR><TD>(단위 : 백만원)</TD></TR></TABLE>"
            '<TABLE BORDER="1"><TR><TD>Assets</TD><TD>100</TD></TR></TABLE>'
        ),
    )

    table = next(grain for grain in compile_document_grains(tree) if grain.kind == GrainKind.TABLE)

    assert table.context.caption == "Consolidated balance sheet As of 2024-12-31"
    assert table.context.unit == "(단위 : 백만원)"
    assert "Assets" in table.core_text
    assert "balance sheet" not in table.core_text


def test_all_empty_layout_table_is_not_a_runtime_grain(tmp_path: Path) -> None:
    tree, _ = compile_fixture(
        tmp_path,
        (
            '<TABLE BORDER="0"><TR><TD></TD><TD></TD></TR></TABLE>'
            '<TABLE BORDER="1"><TR><TD>Assets</TD><TD></TD></TR></TABLE>'
        ),
    )

    tables = tuple(
        grain for grain in compile_document_grains(tree) if grain.kind == GrainKind.TABLE
    )

    assert len(tables) == 1
    assert "c1=Assets | c2=∅" in tables[0].core_text


def test_grains_have_stable_ids_and_bidirectional_neighbor_links(tmp_path: Path) -> None:
    tree, _ = compile_fixture(
        tmp_path,
        (
            '<SECTION-1><TITLE ATOC="Y">Overview</TITLE>'
            "<P>First statement.</P><P>Second statement.</P>"
            '<TITLE ATOC="Y">Details</TITLE><P>Third statement.</P></SECTION-1>'
        ),
    )

    first = compile_document_grains(tree, max_estimated_tokens=10)
    second = compile_document_grains(tree, max_estimated_tokens=10)

    assert tuple(grain.grain_id for grain in first) == tuple(grain.grain_id for grain in second)
    assert [grain.source.ordinal for grain in first] == list(range(len(first)))
    for left, right in zip(first, first[1:], strict=False):
        assert left.next_grain_id == right.grain_id
        assert right.previous_grain_id == left.grain_id
    assert first[0].previous_grain_id is None
    assert first[-1].next_grain_id is None


def test_long_text_splits_into_non_overlapping_exact_subranges(tmp_path: Path) -> None:
    tree, source_bytes = compile_fixture(
        tmp_path,
        '<SECTION-1><TITLE ATOC="Y">Long note</TITLE>'
        "<P>alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi "
        "omicron pi rho sigma tau upsilon phi chi psi omega</P>"
        "</SECTION-1>",
    )

    grains = compile_document_grains(tree, max_estimated_tokens=10)
    ranges = [source_range for grain in grains for source_range in grain.source.core_ranges]

    assert len(grains) > 1
    assert all(left.end_byte <= right.start_byte for left, right in zip(ranges, ranges[1:]))
    assert all(source_bytes[item.start_byte : item.end_byte].strip() for item in ranges)


def test_table_keeps_empty_cell_positions_and_spans(
    tmp_path: Path,
) -> None:
    tree, _ = compile_fixture(
        tmp_path,
        (
            '<SECTION-1><TITLE ATOC="Y" ATOCID="7" AASSOCNOTE="D-1" '
            'ENG="Financial position">Finance</TITLE>'
            '<TABLE><TBODY><TR><TD ROWSPAN="2"></TD>'
            '<TD COLSPAN="2" AUNIT="AMOUNT" AUNITVALUE="100">100</TD></TR>'
            "</TBODY></TABLE>"
            '<A HREF="https://example.test/report">Related report</A>'
            "</SECTION-1>"
        ),
    )

    grains = compile_document_grains(tree, max_estimated_tokens=100)
    table = next(grain for grain in grains if grain.kind == GrainKind.TABLE)

    assert "r1: c1[rowspan=2]=∅ | c2[colspan=2]=100" in table.core_text
    assert not hasattr(table.context, "attributes")


def test_oversized_row_still_keeps_an_empty_cell_grain(tmp_path: Path) -> None:
    tree, _ = compile_fixture(
        tmp_path,
        (
            '<SECTION-1><TITLE ATOC="Y">Finance</TITLE><TABLE><TBODY><TR>'
            '<TD ROWSPAN="2"></TD><TD>'
            "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi "
            "omicron pi rho sigma tau upsilon phi chi psi omega"
            "</TD></TR></TBODY></TABLE></SECTION-1>"
        ),
    )

    grains = compile_document_grains(tree, max_estimated_tokens=35)
    empty = next(grain for grain in grains if "c1[rowspan=2]=∅" in grain.core_text)

    assert empty.context.table_position.startswith("row 1, column")
    assert empty.source.core_ranges


def test_empty_section_heading_becomes_retrievable_core_text(tmp_path: Path) -> None:
    tree, _ = compile_fixture(
        tmp_path,
        (
            '<SECTION-1><TITLE ATOC="Y">Expert review</TITLE><P></P>'
            '<SECTION-2><TITLE ATOC="Y">Independence</TITLE><P></P></SECTION-2>'
            "</SECTION-1>"
        ),
    )

    grains = compile_document_grains(tree, max_estimated_tokens=100)
    child = next(grain for grain in grains if grain.core_text == "Independence")

    assert child.context.heading_path == ("Expert review",)
    assert any(grain.context.heading_path == ("Expert review",) for grain in grains)


def test_wide_table_repeats_only_headers_relevant_to_split_cell(tmp_path: Path) -> None:
    headers = "".join(f"<TH>column-{index} " + "label " * 12 + "</TH>" for index in range(1, 21))
    values = "".join(f"<TD>value-{index}</TD>" for index in range(1, 21))
    tree, _ = compile_fixture(
        tmp_path,
        f"<TABLE><THEAD><TR>{headers}</TR></THEAD><TBODY><TR>{values}</TR></TBODY></TABLE>",
    )

    grains = compile_document_grains(tree, max_estimated_tokens=80)
    table_grains = tuple(grain for grain in grains if grain.kind == GrainKind.TABLE)
    last = next(grain for grain in table_grains if "c20=value-20" in grain.core_text)

    assert any(header.startswith("r1: c20=column-20") for header in last.context.table_headers)
    assert all("c1=column-1" not in header for header in last.context.table_headers)
    assert len(table_grains) < 20
    assert all(grain.estimated_tokens <= 80 for grain in grains)

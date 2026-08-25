import html
from pathlib import Path

import pytest
from pydantic import ValidationError

from evidence.compiler import compile_document_tree
from evidence.document_tree import (
    ArtifactTree,
    Attribute,
    DocumentTree,
    Node,
    NodeKind,
    SourceKind,
    Text,
    walk_nodes,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = PROJECT_ROOT / "corpus"


def source_named(name: str) -> Path:
    return next(CORPUS_ROOT.rglob(name))


def compile_source(name: str, doc_id: str) -> DocumentTree:
    return compile_document_tree(
        source_named(name),
        doc_id=doc_id,
        corpus_root=CORPUS_ROOT,
    )


def artifact_nodes(artifact: ArtifactTree) -> tuple[Node, ...]:
    return walk_nodes(artifact.root)


def texts(node: Node) -> tuple[Text, ...]:
    result: list[Text] = []
    for item in node.content:
        if isinstance(item, Text):
            result.append(item)
        else:
            result.extend(texts(item))
    return tuple(result)


def test_exchange_markup_is_not_reduced_to_a_table() -> None:
    tree = compile_source("20230630800101.xml", "exchange_20230630800101")
    artifact = tree.artifacts[0]
    nodes = artifact_nodes(artifact)

    assert tree.schema_version == "1.0"
    assert artifact.source_kind == SourceKind.EXCHANGE_HTML
    assert artifact.title is not None
    assert artifact.title.display_value == "단일판매ㆍ공급계약 체결"
    assert {NodeKind.DOCUMENT, NodeKind.CONTAINER, NodeKind.TABLE} <= {node.kind for node in nodes}
    assert any(text.display_value == "방위사업청" for text in texts(artifact.root))


def test_dart_xml_preserves_document_nodes() -> None:
    tree = compile_source("20250515002501.xml", "periodic_20250515002501")
    artifact = tree.artifacts[0]
    kinds = {node.kind for node in artifact_nodes(artifact)}

    assert artifact.source_kind == SourceKind.DART_XML
    assert artifact.title is not None
    assert {
        NodeKind.METADATA,
        NodeKind.SECTION,
        NodeKind.HEADING,
        NodeKind.PARAGRAPH,
        NodeKind.TABLE,
        NodeKind.TABLE_ROW,
        NodeKind.TABLE_CELL,
        NodeKind.PAGE_BREAK,
    } <= kinds


def test_dart_xml_preserves_images_and_captions() -> None:
    tree = compile_source("20251001000350.xml", "holding_20251001000350")
    kinds = {node.kind for node in artifact_nodes(tree.artifacts[0])}

    assert NodeKind.IMAGE in kinds
    assert NodeKind.CAPTION in kinds


def test_major_filing_uses_the_same_tree() -> None:
    tree = compile_source("20230420000185.xml", "major_20230420000185")
    artifact = tree.artifacts[0]
    kinds = {node.kind for node in artifact_nodes(artifact)}

    assert artifact.source_kind == SourceKind.DART_XML
    assert {NodeKind.SECTION, NodeKind.HEADING, NodeKind.PARAGRAPH, NodeKind.TABLE} <= kinds


def test_correction_wrapper_is_preserved_as_metadata() -> None:
    tree = compile_source("20230417000426.xml", "holding_20230417000426")
    correction = next(
        node
        for node in artifact_nodes(tree.artifacts[0])
        if node.source_tag.lower() == "correction"
    )

    assert correction.kind == NodeKind.METADATA


def test_viewer_html_preserves_non_table_blocks() -> None:
    tree = compile_source(
        "20260513000860_viewer.html",
        "periodic_20260513000860",
    )
    artifact = tree.artifacts[0]
    kinds = {node.kind for node in artifact_nodes(artifact)}

    assert artifact.source_kind == SourceKind.VIEWER_HTML
    assert {NodeKind.PARAGRAPH, NodeKind.TABLE, NodeKind.LINK, NodeKind.LINE_BREAK} <= kinds


def test_disclosure_directory_compiles_every_xml_artifact() -> None:
    primary = source_named("20240318000916.xml")
    tree = compile_document_tree(
        primary.parent,
        doc_id="periodic_20240318000916",
        corpus_root=CORPUS_ROOT,
    )

    assert len(tree.artifacts) == 3
    assert tree.artifacts[0].source_path.endswith("/20240318000916.xml")
    assert {artifact.source_kind for artifact in tree.artifacts} == {SourceKind.DART_XML}


def test_pdf_fallback_directory_compiles_viewer_html_only() -> None:
    pdf = source_named("20240514001522.pdf")
    tree = compile_document_tree(
        pdf.parent,
        doc_id="periodic_20240514001522",
        corpus_root=CORPUS_ROOT,
    )

    assert len(tree.artifacts) == 1
    assert tree.artifacts[0].source_kind == SourceKind.VIEWER_HTML
    assert tree.artifacts[0].source_path.endswith("/20240514001522_viewer.html")


def test_each_text_keeps_raw_and_display_values_with_source_bytes() -> None:
    tree = compile_source("20230630800101.xml", "exchange_20230630800101")
    artifact = tree.artifacts[0]
    source_bytes = source_named("20230630800101.xml").read_bytes()

    for text in texts(artifact.root):
        source = text.source
        source_slice = source_bytes[source.start_byte : source.end_byte].decode("utf-8")
        assert source_slice == text.raw_value
        assert " ".join(html.unescape(source_slice).split()) == text.display_value
        assert source.artifact_id == artifact.artifact_id
        assert source.source_path == artifact.source_path


def test_bare_ampersand_is_not_changed_or_given_an_overlapping_range(tmp_path: Path) -> None:
    receipt_no = "20230101000001"
    source_directory = tmp_path / receipt_no
    source_directory.mkdir()
    source_file = source_directory / f"{receipt_no}.xml"
    source_file.write_text(
        "<DOCUMENT><BODY><P>AT&T, R&amp;D, A&#38;B</P></BODY></DOCUMENT>",
        encoding="utf-8",
    )

    tree = compile_document_tree(
        source_file,
        doc_id=f"periodic_{receipt_no}",
        corpus_root=tmp_path,
    )
    paragraph = next(
        node for node in artifact_nodes(tree.artifacts[0]) if node.kind == NodeKind.PARAGRAPH
    )
    paragraph_texts = texts(paragraph)

    assert "".join(text.raw_value for text in paragraph_texts) == "AT&T, R&amp;D, A&#38;B"
    assert "".join(text.display_value for text in paragraph_texts) == "AT&T, R&D, A&B"
    assert all(
        left.source.end_byte == right.source.start_byte
        for left, right in zip(paragraph_texts, paragraph_texts[1:], strict=False)
    )


def test_unknown_tags_remain_immutable_nodes(tmp_path: Path) -> None:
    receipt_no = "20230101000001"
    source_directory = tmp_path / receipt_no
    source_directory.mkdir()
    source_file = source_directory / f"{receipt_no}.xml"
    source_file.write_text(
        '<DOCUMENT><BODY><ODD-TAG USERMARK="1">kept</ODD-TAG></BODY></DOCUMENT>',
        encoding="utf-8",
    )

    tree = compile_document_tree(
        source_file,
        doc_id=f"periodic_{receipt_no}",
        corpus_root=tmp_path,
    )
    odd_tag = next(
        node for node in artifact_nodes(tree.artifacts[0]) if node.source_tag.lower() == "odd-tag"
    )

    assert odd_tag.kind == NodeKind.ELEMENT
    assert odd_tag.attributes == (Attribute(name="usermark", value="1"),)
    assert [text.display_value for text in texts(odd_tag)] == ["kept"]
    with pytest.raises(ValidationError):
        odd_tag.attributes[0].value = "changed"


def test_duplicate_attributes_are_kept_in_source_order(tmp_path: Path) -> None:
    receipt_no = "20230101000001"
    source_directory = tmp_path / receipt_no
    source_directory.mkdir()
    source_file = source_directory / f"{receipt_no}.xml"
    source_file.write_text(
        '<DOCUMENT><BODY><P JOINT="first" JOINT="second">kept</P></BODY></DOCUMENT>',
        encoding="utf-8",
    )

    tree = compile_document_tree(
        source_file,
        doc_id=f"periodic_{receipt_no}",
        corpus_root=tmp_path,
    )
    paragraph = next(
        node for node in artifact_nodes(tree.artifacts[0]) if node.kind == NodeKind.PARAGRAPH
    )

    assert paragraph.attributes == (
        Attribute(name="joint", value="first"),
        Attribute(name="joint", value="second"),
    )


def test_real_dart_span_is_a_node_not_literal_markup() -> None:
    tree = compile_source("20250515002501.xml", "periodic_20250515002501")
    artifact = tree.artifacts[0]
    nodes = artifact_nodes(artifact)

    assert any(node.source_tag.lower() == "span" for node in nodes)
    assert all(not text.display_value.startswith("<SPAN") for text in texts(artifact.root))


def test_rejects_pdf_as_tree_source() -> None:
    pdf = source_named("20240514001522.pdf")

    with pytest.raises(ValueError, match="unsupported source artifact"):
        compile_document_tree(
            pdf,
            doc_id="periodic_20240514001522",
            corpus_root=CORPUS_ROOT,
        )


def test_rejects_artifacts_from_another_disclosure() -> None:
    source = source_named("20230630800101.xml")

    with pytest.raises(ValueError, match="does not belong"):
        compile_document_tree(
            source,
            doc_id="exchange_20230630800102",
            corpus_root=CORPUS_ROOT,
        )


def test_rejects_mixed_disclosure_directories(tmp_path: Path) -> None:
    receipt_no = "20230101000001"
    first_directory = tmp_path / "first" / receipt_no
    second_directory = tmp_path / "second" / receipt_no
    first_directory.mkdir(parents=True)
    second_directory.mkdir(parents=True)
    first = first_directory / f"{receipt_no}.xml"
    second = second_directory / f"{receipt_no}_attachment.xml"
    first.write_text("<DOCUMENT><BODY>first</BODY></DOCUMENT>", encoding="utf-8")
    second.write_text("<DOCUMENT><BODY>second</BODY></DOCUMENT>", encoding="utf-8")

    with pytest.raises(ValueError, match="one disclosure directory"):
        compile_document_tree(
            [first, second],
            doc_id=f"periodic_{receipt_no}",
            corpus_root=tmp_path,
        )

from __future__ import annotations

import html
import os
import re
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pytest

from evidence.compiler import compile_document_tree
from evidence.document_tree import ArtifactTree, Node
from evidence.validate_corpus import _index_document_directories, _nfc, _read_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = PROJECT_ROOT / "corpus"
TREE_SUFFIXES = {".xml", ".html"}
EXCLUDED_HEAD_TAGS = {"html", "head", "link", "meta", "script", "style", "title"}
RUN_CORPUS_TEST = os.environ.get("RUN_CORPUS_TAG_ATTRIBUTE_TEST") == "1"
CORPUS_WORKERS = int(os.environ.get("CORPUS_TAG_ATTRIBUTE_WORKERS", "4"))


@dataclass(frozen=True)
class SourceTag:
    name: str
    attributes: tuple[tuple[str, str], ...]
    start_byte: int


@dataclass(frozen=True)
class _CharacterTag:
    name: str
    attributes: tuple[tuple[str, str], ...]
    start_character: int


@dataclass(frozen=True)
class DocumentTask:
    doc_id: str
    directory: Path
    corpus_root: Path


@dataclass(frozen=True)
class DocumentResult:
    artifact_count: int
    failures: tuple[str, ...]


def _tag_end(source: str, start: int) -> int:
    quote: str | None = None
    expects_attribute_value = False
    position = start + 1
    while position < len(source):
        character = source[position]
        if quote is not None:
            if character == quote:
                quote = None
        else:
            if character == ">":
                return position + 1
            if character == "=":
                expects_attribute_value = True
            elif expects_attribute_value:
                if character.isspace():
                    pass
                elif character in {'"', "'"}:
                    quote = character
                    expects_attribute_value = False
                else:
                    expects_attribute_value = False
        position += 1
    return len(source)


def _attributes(start_tag: str, tag_name_end: int) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    position = tag_name_end
    while position < len(start_tag):
        while position < len(start_tag) and start_tag[position].isspace():
            position += 1
        if position >= len(start_tag) or start_tag[position] in "/>":
            break

        name_start = position
        while (
            position < len(start_tag)
            and not start_tag[position].isspace()
            and start_tag[position] not in "=/>"
        ):
            position += 1
        name = start_tag[name_start:position].lower()
        if not name:
            position += 1
            continue

        while position < len(start_tag) and start_tag[position].isspace():
            position += 1
        value = ""
        if position < len(start_tag) and start_tag[position] == "=":
            position += 1
            while position < len(start_tag) and start_tag[position].isspace():
                position += 1
            if position < len(start_tag) and start_tag[position] in {'"', "'"}:
                quote = start_tag[position]
                position += 1
                value_start = position
                while position < len(start_tag) and start_tag[position] != quote:
                    position += 1
                value = start_tag[value_start:position]
                if position < len(start_tag):
                    position += 1
            else:
                value_start = position
                while (
                    position < len(start_tag)
                    and not start_tag[position].isspace()
                    and start_tag[position] not in "/>"
                ):
                    position += 1
                value = start_tag[value_start:position]
        result.append((name, html.unescape(value)))
    return tuple(result)


def scan_source_tags(source: str) -> tuple[SourceTag, ...]:
    character_tags: list[_CharacterTag] = []
    position = 0
    while position < len(source):
        start = source.find("<", position)
        if start < 0:
            break
        if source.startswith("<!--", start):
            comment_end = source.find("-->", start + 4)
            position = len(source) if comment_end < 0 else comment_end + 3
            continue
        if source.startswith("<![CDATA[", start):
            cdata_end = source.find("]]>", start + 9)
            position = len(source) if cdata_end < 0 else cdata_end + 3
            continue
        if source.startswith(("</", "<!", "<?"), start):
            position = _tag_end(source, start)
            continue
        if start + 1 >= len(source) or not re.match(r"[A-Za-z_:]", source[start + 1]):
            position = start + 1
            continue

        end = _tag_end(source, start)
        start_tag = source[start:end]
        name_match = re.match(r"<\s*([^\s/>]+)", start_tag)
        if name_match is None:
            position = end
            continue
        name = name_match.group(1)
        character_tags.append(
            _CharacterTag(
                name=name,
                attributes=_attributes(start_tag, name_match.end()),
                start_character=start,
            )
        )
        position = end

        if name.lower() in {"script", "style"}:
            closing_tag = re.search(rf"</\s*{re.escape(name)}\b", source[position:], re.IGNORECASE)
            if closing_tag is not None:
                position += closing_tag.start()

    result: list[SourceTag] = []
    last_character = 0
    last_byte = 0
    for tag in character_tags:
        last_byte += len(source[last_character : tag.start_character].encode("utf-8"))
        result.append(
            SourceTag(
                name=tag.name,
                attributes=tag.attributes,
                start_byte=last_byte,
            )
        )
        last_character = tag.start_character
    return tuple(result)


def tree_nodes(root: Node) -> tuple[Node, ...]:
    result: list[Node] = []
    stack = [root]
    while stack:
        node = stack.pop()
        result.append(node)
        stack.extend(reversed([item for item in node.content if isinstance(item, Node)]))
    return tuple(result)


def _semantic_source_tags(source_tags: tuple[SourceTag, ...]) -> tuple[SourceTag, ...]:
    body = next((tag for tag in source_tags if tag.name.lower() == "body"), None)
    if body is None:
        return source_tags
    return tuple(
        tag
        for tag in source_tags
        if not (tag.start_byte < body.start_byte and tag.name.lower() in EXCLUDED_HEAD_TAGS)
    )


def compare_source_to_tree(source_file: Path, artifact: ArtifactTree) -> str | None:
    source_tags = scan_source_tags(source_file.read_bytes().decode("utf-8"))
    body = next((tag for tag in source_tags if tag.name.lower() == "body"), None)
    head_title = next(
        (
            tag
            for tag in source_tags
            if tag.name.lower() == "title" and (body is None or tag.start_byte < body.start_byte)
        ),
        None,
    )
    if head_title is not None:
        if artifact.title is None:
            return "head title exists but ArtifactTree.title is missing"
        if artifact.title.source.artifact_id != artifact.artifact_id:
            return "ArtifactTree.title points to another artifact"
        if artifact.title.source.source_path != artifact.source_path:
            return "ArtifactTree.title points to another source path"

    source_tags = _semantic_source_tags(source_tags)
    nodes = tree_nodes(artifact.root)
    if len(source_tags) != len(nodes):
        return f"tag count: source={len(source_tags)} tree={len(nodes)}"

    for index, (source_tag, node) in enumerate(zip(source_tags, nodes, strict=True)):
        tree_attributes = tuple((attribute.name, attribute.value) for attribute in node.attributes)
        if source_tag.start_byte != node.source.start_byte:
            return (
                f"tag[{index}] byte: source={source_tag.start_byte} tree={node.source.start_byte}"
            )
        if source_tag.name != node.source_tag:
            return f"tag[{index}] name: source={source_tag.name!r} tree={node.source_tag!r}"
        if source_tag.attributes != tree_attributes:
            return (
                f"tag[{index}] {source_tag.name} attributes: "
                f"source={source_tag.attributes!r} tree={tree_attributes!r}"
            )
    return None


def check_document(task: DocumentTask) -> DocumentResult:
    try:
        source_files = tuple(
            path
            for path in task.directory.iterdir()
            if path.is_file() and path.suffix.lower() in TREE_SUFFIXES
        )
        tree = compile_document_tree(
            task.directory,
            doc_id=task.doc_id,
            corpus_root=task.corpus_root,
        )
        artifacts = {artifact.source_path: artifact for artifact in tree.artifacts}
        expected_paths = {path.relative_to(task.corpus_root).as_posix() for path in source_files}
        if set(artifacts) != expected_paths:
            return DocumentResult(
                artifact_count=0,
                failures=(f"{task.doc_id}: artifact path coverage mismatch",),
            )

        failures: list[str] = []
        for source_file in source_files:
            source_path = source_file.relative_to(task.corpus_root).as_posix()
            mismatch = compare_source_to_tree(source_file, artifacts[source_path])
            if mismatch is not None:
                failures.append(f"{task.doc_id} {source_path}: {mismatch}")
        return DocumentResult(
            artifact_count=len(source_files),
            failures=tuple(failures),
        )
    except Exception as error:
        return DocumentResult(
            artifact_count=0,
            failures=(f"{task.doc_id}: {type(error).__name__}: {error}",),
        )


def test_source_scanner_keeps_tag_attribute_order_and_duplicates() -> None:
    source = '<ROOT B="1" A="&amp;" B="2"><CHILD FLAG/></ROOT>'

    assert scan_source_tags(source) == (
        SourceTag(name="ROOT", attributes=(("b", "1"), ("a", "&"), ("b", "2")), start_byte=0),
        SourceTag(name="CHILD", attributes=(("flag", ""),), start_byte=28),
    )


def test_compare_preserves_bom_and_crlf_byte_offsets(tmp_path: Path) -> None:
    receipt_no = "20230101000001"
    source_file = tmp_path / f"{receipt_no}.xml"
    source_file.write_bytes(
        '\ufeff<?xml version="1.0"?>\r\n<ROOT A="1"><CHILD/></ROOT>'.encode("utf-8")
    )
    tree = compile_document_tree(
        source_file,
        doc_id=f"periodic_{receipt_no}",
        corpus_root=tmp_path,
    )

    assert compare_source_to_tree(source_file, tree.artifacts[0]) is None


def test_compare_tolerates_stray_quote_after_attribute_value(tmp_path: Path) -> None:
    receipt_no = "20230101000001"
    source_file = tmp_path / f"{receipt_no}.xml"
    source_file.write_text(
        '<DOCUMENT><BODY><P ENG="Other receivables"">Text</P><P>Next</P></BODY></DOCUMENT>',
        encoding="utf-8",
    )
    tree = compile_document_tree(
        source_file,
        doc_id=f"periodic_{receipt_no}",
        corpus_root=tmp_path,
    )

    assert compare_source_to_tree(source_file, tree.artifacts[0]) is None


def test_ignores_known_head_tags_and_checks_title_separately(tmp_path: Path) -> None:
    receipt_no = "20230101000001"
    source_file = tmp_path / f"{receipt_no}.html"
    source_file.write_text(
        '<html><head><meta charset="utf-8"><link rel="stylesheet" href="viewer.css">'
        '<script src="viewer.js"></script><style>p{color:red}</style>'
        "<title>Head title</title></head><body><h1>Visible title</h1></body></html>",
        encoding="utf-8",
    )
    tree = compile_document_tree(
        source_file,
        doc_id=f"exchange_{receipt_no}",
        corpus_root=tmp_path,
    )

    assert tree.artifacts[0].title is not None
    assert compare_source_to_tree(source_file, tree.artifacts[0]) is None


def test_does_not_ignore_unknown_head_tags(tmp_path: Path) -> None:
    receipt_no = "20230101000001"
    source_file = tmp_path / f"{receipt_no}.html"
    source_file.write_text(
        '<html><head><title>Title</title><domain-data value="keep"/></head>'
        "<body><h1>Visible title</h1></body></html>",
        encoding="utf-8",
    )
    tree = compile_document_tree(
        source_file,
        doc_id=f"exchange_{receipt_no}",
        corpus_root=tmp_path,
    )

    assert compare_source_to_tree(source_file, tree.artifacts[0]) == "tag count: source=3 tree=2"


def test_checks_one_document_task(tmp_path: Path) -> None:
    receipt_no = "20230101000001"
    directory = tmp_path / receipt_no
    directory.mkdir()
    (directory / f"{receipt_no}.xml").write_text(
        '<DOCUMENT><BODY><P A="1" A="2">Text</P></BODY></DOCUMENT>',
        encoding="utf-8",
    )

    result = check_document(
        DocumentTask(
            doc_id=f"periodic_{receipt_no}",
            directory=directory,
            corpus_root=tmp_path,
        )
    )

    assert result.artifact_count == 1
    assert not result.failures


@pytest.mark.corpus
@pytest.mark.skipif(
    not RUN_CORPUS_TEST,
    reason="set RUN_CORPUS_TAG_ATTRIBUTE_TEST=1 to scan the full corpus",
)
def test_every_source_tag_and_attribute_is_in_document_tree() -> None:
    documents = _read_manifest(CORPUS_ROOT)
    directories = _index_document_directories(CORPUS_ROOT)
    assert CORPUS_WORKERS >= 1, "CORPUS_TAG_ATTRIBUTE_WORKERS must be at least 1"
    tasks = tuple(
        DocumentTask(
            doc_id=document.doc_id,
            directory=directories[_nfc(document.file_path)],
            corpus_root=CORPUS_ROOT,
        )
        for document in documents
    )
    failures: list[str] = []
    checked_artifacts = 0

    with ProcessPoolExecutor(max_workers=CORPUS_WORKERS) as executor:
        results = executor.map(check_document, tasks, chunksize=1)
        for position, result in enumerate(results, start=1):
            checked_artifacts += result.artifact_count
            failures.extend(result.failures)
            if position % 100 == 0:
                print(
                    f"checked {position}/{len(documents)} documents, "
                    f"{checked_artifacts} artifacts; failures={len(failures)}",
                    flush=True,
                )

    failure_preview = "\n".join(failures[:100])
    assert not failures, (
        f"{len(failures)} artifacts failed tag/attribute coverage:\n{failure_preview}"
    )

from __future__ import annotations

import argparse
import hashlib
import html
import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from evidence.document_tree import (
    ArtifactTree,
    Attribute,
    DocumentTree,
    Node,
    NodeKind,
    SourceKind,
    SourceRange,
    Text,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

VOID_HTML_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


@dataclass
class _TextFragment:
    value: str
    start_character: int
    end_character: int


@dataclass
class _Element:
    tag: str
    source_tag: str
    attributes: list[tuple[str, str]]
    xpath: str
    start_character: int
    end_character: int | None = None
    content: list[_TextFragment | _Element] = field(default_factory=list)

    def attribute(self, name: str) -> str:
        for attribute_name, value in reversed(self.attributes):
            if attribute_name == name:
                return value
        return ""

    def descendants(self, tag: str) -> list[_Element]:
        result: list[_Element] = []
        for item in self.content:
            if not isinstance(item, _Element):
                continue
            if item.tag == tag:
                result.append(item)
            result.extend(item.descendants(tag))
        return result


class _SourceHTMLParser(HTMLParser):
    def __init__(self, source: str, *, dart_mode: bool) -> None:
        super().__init__(convert_charrefs=False)
        self.source = source
        self.dart_mode = dart_mode
        self.roots: list[_Element] = []
        self.stack: list[_Element] = []
        self.line_starts = [0]
        for position, character in enumerate(source):
            if character == "\n":
                self.line_starts.append(position + 1)

    def _character_offset(self) -> int:
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    def _append_content(self, item: _TextFragment | _Element) -> None:
        if self.stack:
            self.stack[-1].content.append(item)
        elif isinstance(item, _Element):
            self.roots.append(item)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        raw_start_tag = self.get_starttag_text() or f"<{tag}>"
        parent = self.stack[-1] if self.stack else None
        siblings = (
            [item for item in parent.content if isinstance(item, _Element)]
            if parent
            else self.roots
        )
        sibling_index = sum(sibling.tag == tag for sibling in siblings) + 1
        parent_xpath = parent.xpath if parent else ""
        source_tag_match = re.match(r"<\s*([^\s/>]+)", raw_start_tag)
        source_tag = source_tag_match.group(1) if source_tag_match else tag
        start_character = self._character_offset()
        element = _Element(
            tag=tag,
            source_tag=source_tag,
            attributes=[(name, value or "") for name, value in attrs],
            xpath=f"{parent_xpath}/{tag}[{sibling_index}]",
            start_character=start_character,
        )
        self._append_content(element)
        is_void = tag in VOID_HTML_TAGS and not self.dart_mode
        if is_void:
            element.end_character = start_character + len(raw_start_tag)
        else:
            self.stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self.stack and self.stack[-1].tag == tag:
            raw_start_tag = self.get_starttag_text() or f"<{tag}/>"
            self.stack[-1].end_character = self._character_offset() + len(raw_start_tag)
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].tag != tag:
                continue
            end_start = self._character_offset()
            end_character = self.source.find(">", end_start)
            self.stack[index].end_character = (
                end_character + 1 if end_character >= 0 else len(self.source)
            )
            for unclosed in self.stack[index + 1 :]:
                unclosed.end_character = end_start
            del self.stack[index:]
            return

    def handle_data(self, data: str) -> None:
        if not self.stack or not data:
            return
        start = self._character_offset()
        self.stack[-1].content.append(
            _TextFragment(data, start_character=start, end_character=start + len(data))
        )

    def handle_entityref(self, name: str) -> None:
        self._append_reference(name, prefix="&")

    def handle_charref(self, name: str) -> None:
        self._append_reference(name, prefix="&#")

    def _append_reference(self, name: str, *, prefix: str) -> None:
        if not self.stack:
            return
        start = self._character_offset()
        end = start + len(prefix) + len(name)
        if self.source[end : end + 1] == ";":
            end += 1
        reference = self.source[start:end]
        self.stack[-1].content.append(
            _TextFragment(
                html.unescape(reference),
                start_character=start,
                end_character=end,
            )
        )

    def close_open_elements(self) -> None:
        for element in self.stack:
            element.end_character = len(self.source)
        self.stack.clear()


def _all_elements(element: _Element) -> tuple[_Element, ...]:
    children = (item for item in element.content if isinstance(item, _Element))
    return (element, *(descendant for child in children for descendant in _all_elements(child)))


def _all_text_fragments(element: _Element) -> tuple[_TextFragment, ...]:
    result: list[_TextFragment] = []
    for item in element.content:
        if isinstance(item, _TextFragment):
            result.append(item)
        else:
            result.extend(_all_text_fragments(item))
    return tuple(result)


def _trimmed_fragment_range(fragment: _TextFragment) -> tuple[int, int] | None:
    if not fragment.value.strip():
        return None
    leading = len(fragment.value) - len(fragment.value.lstrip())
    trailing = len(fragment.value) - len(fragment.value.rstrip())
    return fragment.start_character + leading, fragment.end_character - trailing


class _ByteOffsets:
    def __init__(self, source: str, roots: list[_Element]) -> None:
        positions = {0}
        for root in roots:
            for element in _all_elements(root):
                positions.add(element.start_character)
                positions.add(element.end_character or len(source))
                for fragment in _all_text_fragments(element):
                    trimmed_range = _trimmed_fragment_range(fragment)
                    if trimmed_range is not None:
                        positions.update(trimmed_range)

        self.offsets: dict[int, int] = {}
        last_character = 0
        last_byte = 0
        for position in sorted(positions):
            last_byte += len(source[last_character:position].encode("utf-8"))
            self.offsets[position] = last_byte
            last_character = position

    def __getitem__(self, character_offset: int) -> int:
        return self.offsets[character_offset]


def _artifact_identity(source_file: Path, corpus_root: Path) -> tuple[str, str]:
    source_path = source_file.relative_to(corpus_root).as_posix()
    return unicodedata.normalize("NFC", source_path), source_path


def _markup_locator(
    element: _Element,
    *,
    artifact_id: str,
    source_path: str,
    byte_offsets: _ByteOffsets,
) -> SourceRange:
    if element.end_character is None:
        raise ValueError(f"element has no source end: {element.xpath}")
    return SourceRange(
        artifact_id=artifact_id,
        source_path=source_path,
        xpath=element.xpath,
        start_byte=byte_offsets[element.start_character],
        end_byte=byte_offsets[element.end_character],
    )


def _located_fragment(
    fragment: _TextFragment,
    *,
    parent: _Element,
    artifact_id: str,
    source_path: str,
    source_text: str,
    byte_offsets: _ByteOffsets,
) -> Text | None:
    trimmed_range = _trimmed_fragment_range(fragment)
    if trimmed_range is None:
        return None
    start_character, end_character = trimmed_range
    return Text(
        raw_value=source_text[start_character:end_character],
        display_value=" ".join(fragment.value.strip().split()),
        source=SourceRange(
            artifact_id=artifact_id,
            source_path=source_path,
            xpath=f"{parent.xpath}/text()",
            start_byte=byte_offsets[start_character],
            end_byte=byte_offsets[end_character],
        ),
    )


def _node_kind(tag: str) -> NodeKind:
    if tag in {"document", "html", "body"}:
        return NodeKind.DOCUMENT
    if tag in {
        "company-name",
        "correction",
        "document-name",
        "extraction",
        "formula-version",
        "head",
        "meta",
        "summary",
    }:
        return NodeKind.METADATA
    if tag in {"cover", "library"} or re.fullmatch(r"section-[0-9]+", tag):
        return NodeKind.SECTION
    if tag in {"cover-title", "title", "h1", "h2", "h3", "h4", "h5", "h6"}:
        return NodeKind.HEADING
    if tag == "p":
        return NodeKind.PARAGRAPH
    if tag == "table-group":
        return NodeKind.TABLE_GROUP
    if tag == "table":
        return NodeKind.TABLE
    if tag == "thead":
        return NodeKind.TABLE_HEAD
    if tag == "tbody":
        return NodeKind.TABLE_BODY
    if tag == "tr":
        return NodeKind.TABLE_ROW
    if tag in {"td", "te", "th", "tu"}:
        return NodeKind.TABLE_CELL
    if tag in {"image", "img"}:
        return NodeKind.IMAGE
    if tag in {"caption", "img-caption"}:
        return NodeKind.CAPTION
    if tag == "pgbrk":
        return NodeKind.PAGE_BREAK
    if tag == "a":
        return NodeKind.LINK
    if tag == "br":
        return NodeKind.LINE_BREAK
    if tag in {"div", "span", "col", "colgroup"}:
        return NodeKind.CONTAINER
    return NodeKind.ELEMENT


def _node(
    element: _Element,
    *,
    artifact_id: str,
    source_path: str,
    source_text: str,
    byte_offsets: _ByteOffsets,
) -> Node:
    content: list[Text | Node] = []
    for item in element.content:
        if isinstance(item, _TextFragment):
            located = _located_fragment(
                item,
                parent=element,
                artifact_id=artifact_id,
                source_path=source_path,
                source_text=source_text,
                byte_offsets=byte_offsets,
            )
            if located is not None:
                content.append(located)
        else:
            content.append(
                _node(
                    item,
                    artifact_id=artifact_id,
                    source_path=source_path,
                    source_text=source_text,
                    byte_offsets=byte_offsets,
                )
            )
    return Node(
        kind=_node_kind(element.tag),
        source_tag=element.source_tag,
        attributes=tuple(Attribute(name=name, value=value) for name, value in element.attributes),
        source=_markup_locator(
            element,
            artifact_id=artifact_id,
            source_path=source_path,
            byte_offsets=byte_offsets,
        ),
        content=tuple(content),
    )


def _element_text(element: _Element) -> str:
    fragments = _all_text_fragments(element)
    return " ".join("".join(fragment.value for fragment in fragments).split())


def _title_element(root: _Element, source_kind: SourceKind) -> _Element | None:
    elements = _all_elements(root)
    if source_kind == SourceKind.DART_XML:
        for tag in ("cover-title", "document-name", "title"):
            candidate = next(
                (element for element in elements if element.tag == tag and _element_text(element)),
                None,
            )
            if candidate is not None:
                return candidate
        return None

    cover_title = next(
        (
            element
            for element in elements
            if "cover-title" in element.attribute("class").split() and _element_text(element)
        ),
        None,
    )
    if cover_title is not None:
        return cover_title
    visible_title = next(
        (
            element
            for element in elements
            if element.tag == "span"
            and "font-weight:bold" in element.attribute("style").replace(" ", "")
            and _element_text(element)
        ),
        None,
    )
    if visible_title is not None:
        return visible_title
    return next(
        (element for element in elements if element.tag == "title" and _element_text(element)),
        None,
    )


def _located_element_text(
    element: _Element,
    *,
    artifact_id: str,
    source_path: str,
    source_text: str,
    byte_offsets: _ByteOffsets,
) -> Text:
    text_fragments = _all_text_fragments(element)
    return Text(
        raw_value="".join(
            source_text[fragment.start_character : fragment.end_character]
            for fragment in text_fragments
        ),
        display_value=_element_text(element),
        source=_markup_locator(
            element,
            artifact_id=artifact_id,
            source_path=source_path,
            byte_offsets=byte_offsets,
        ),
    )


def _compile_markup_artifact(source_file: Path, corpus_root: Path) -> ArtifactTree:
    source_bytes = source_file.read_bytes()
    try:
        source_text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"source is not UTF-8: {source_file}") from error

    dart_mode = bool(re.search(r"<DOCUMENT(?:\s|>)", source_text[:1000], re.IGNORECASE))
    parser = _SourceHTMLParser(source_text, dart_mode=dart_mode)
    parser.feed(source_text)
    parser.close_open_elements()
    if not parser.roots:
        raise ValueError(f"source has no markup root: {source_file}")

    document_root = next(
        (element for element in parser.roots if element.tag in {"document", "html"}),
        parser.roots[0],
    )
    source_kind = (
        SourceKind.DART_XML
        if document_root.tag == "document"
        else SourceKind.VIEWER_HTML
        if source_file.name.endswith("_viewer.html")
        else SourceKind.EXCHANGE_HTML
    )
    content_root = document_root
    if document_root.tag == "html":
        content_root = next(iter(document_root.descendants("body")), document_root)

    artifact_id, source_path = _artifact_identity(source_file, corpus_root)
    byte_offsets = _ByteOffsets(source_text, parser.roots)
    title_element = _title_element(document_root, source_kind)
    return ArtifactTree(
        artifact_id=artifact_id,
        source_path=source_path,
        source_format=source_file.suffix.lower().lstrip("."),
        source_kind=source_kind,
        byte_size=len(source_bytes),
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        title=(
            _located_element_text(
                title_element,
                artifact_id=artifact_id,
                source_path=source_path,
                source_text=source_text,
                byte_offsets=byte_offsets,
            )
            if title_element is not None
            else None
        ),
        root=_node(
            content_root,
            artifact_id=artifact_id,
            source_path=source_path,
            source_text=source_text,
            byte_offsets=byte_offsets,
        ),
    )


type SourceInput = Path | tuple[Path, ...] | list[Path]


def _source_files(source: SourceInput, doc_id: str) -> tuple[Path, ...]:
    receipt_no = doc_id.rsplit("_", maxsplit=1)[-1]
    if not re.fullmatch(r"[0-9]{14}", receipt_no):
        raise ValueError(f"doc_id must end with a 14-digit receipt number: {doc_id}")

    candidates: tuple[Path, ...]
    if isinstance(source, Path):
        if source.is_file():
            candidates = (source,)
        else:
            if not source.is_dir():
                raise FileNotFoundError(source)
            candidates = tuple(
                path
                for path in source.iterdir()
                if path.is_file() and path.suffix.lower() in {".xml", ".html"}
            )
    else:
        candidates = tuple(source)
    if not candidates:
        raise ValueError("DocumentTree requires at least one XML or HTML source artifact")

    supported_suffixes = {".xml", ".html"}
    resolved_paths: set[Path] = set()
    parent_directories: set[Path] = set()
    for path in candidates:
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.suffix.lower() not in supported_suffixes:
            raise ValueError(f"unsupported source artifact: {path}")
        if not path.name.startswith(receipt_no):
            raise ValueError(f"source artifact does not belong to {doc_id}: {path}")
        resolved_path = path.resolve()
        if resolved_path in resolved_paths:
            raise ValueError(f"duplicate source artifact: {path}")
        resolved_paths.add(resolved_path)
        parent_directories.add(resolved_path.parent)

    if len(parent_directories) != 1:
        raise ValueError("all source artifacts must belong to one disclosure directory")

    def artifact_order(path: Path) -> tuple[int, str]:
        if path.stem == receipt_no:
            return 0, path.name
        if path.name == f"{receipt_no}_viewer.html":
            return 2, path.name
        return 1, path.name

    return tuple(sorted(candidates, key=artifact_order))


def compile_document_tree(
    source: SourceInput,
    *,
    doc_id: str,
    corpus_root: Path,
) -> DocumentTree:
    artifacts = tuple(
        _compile_markup_artifact(path, corpus_root) for path in _source_files(source, doc_id)
    )
    return DocumentTree(doc_id=doc_id, artifacts=artifacts)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile every XML/HTML artifact of one disclosure to DocumentTree JSON."
    )
    parser.add_argument("doc_id")
    parser.add_argument("source", type=Path, help="Source artifact or disclosure directory")
    parser.add_argument("--corpus-root", type=Path, default=PROJECT_ROOT / "corpus")
    arguments = parser.parse_args()

    document = compile_document_tree(
        arguments.source.resolve(),
        doc_id=arguments.doc_id,
        corpus_root=arguments.corpus_root.resolve(),
    )
    print(document.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

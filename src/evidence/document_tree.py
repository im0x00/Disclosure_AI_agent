from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceRange(BaseModel):
    """Exact range of an element or text value in an immutable source artifact."""

    model_config = ConfigDict(frozen=True)

    artifact_id: str
    source_path: str
    xpath: str
    start_byte: int = Field(ge=0)
    end_byte: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_byte_range(self) -> SourceRange:
        if self.end_byte <= self.start_byte:
            raise ValueError("end_byte must be greater than start_byte")
        return self


class Text(BaseModel):
    """Source text plus the whitespace-normalized value shown to downstream readers."""

    model_config = ConfigDict(frozen=True)

    raw_value: str = Field(min_length=1)
    display_value: str = Field(min_length=1)
    source: SourceRange


class NodeKind(StrEnum):
    DOCUMENT = "document"
    METADATA = "metadata"
    SECTION = "section"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE_GROUP = "table_group"
    TABLE = "table"
    TABLE_HEAD = "table_head"
    TABLE_BODY = "table_body"
    TABLE_ROW = "table_row"
    TABLE_CELL = "table_cell"
    IMAGE = "image"
    CAPTION = "caption"
    PAGE_BREAK = "page_break"
    LINK = "link"
    LINE_BREAK = "line_break"
    CONTAINER = "container"
    ELEMENT = "element"


class Attribute(BaseModel):
    """One immutable source attribute, kept in source order."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    value: str


class Node(BaseModel):
    """One ordered XML/HTML element with common meaning and source detail."""

    model_config = ConfigDict(frozen=True)

    kind: NodeKind
    source_tag: str
    attributes: tuple[Attribute, ...] = ()
    source: SourceRange
    content: tuple[Text | Node, ...] = ()


class SourceKind(StrEnum):
    DART_XML = "dart_xml"
    EXCHANGE_HTML = "exchange_html"
    VIEWER_HTML = "viewer_html"


class ArtifactTree(BaseModel):
    """Tree compiled from one XML or HTML source artifact."""

    model_config = ConfigDict(frozen=True)

    artifact_id: str
    source_path: str
    source_format: str
    source_kind: SourceKind
    byte_size: int = Field(ge=0)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    title: Text | None = None
    root: Node


class DocumentTree(BaseModel):
    """One disclosure represented by every XML/HTML artifact in source order."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    compiler_version: Literal["1.0"] = "1.0"
    doc_id: str
    artifacts: tuple[ArtifactTree, ...] = Field(min_length=1)


def walk_nodes(node: Node) -> tuple[Node, ...]:
    """Return a depth-first view while preserving source order."""

    children = (item for item in node.content if isinstance(item, Node))
    return (node, *(descendant for child in children for descendant in walk_nodes(child)))

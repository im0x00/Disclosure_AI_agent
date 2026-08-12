"""Immutable models for byte-lossless disclosure parsing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class SourceFormat(StrEnum):
    DART_MARKUP = "dart-markup"
    HTML = "html"
    JSON = "json"
    PDF = "pdf"
    UNKNOWN = "unknown"


class TokenKind(StrEnum):
    XML_DECLARATION = "xml-declaration"
    PROCESSING_INSTRUCTION = "processing-instruction"
    DOCTYPE = "doctype"
    COMMENT = "comment"
    CDATA = "cdata"
    START_TAG = "start-tag"
    END_TAG = "end-tag"
    SELF_CLOSING_TAG = "self-closing-tag"
    TEXT = "text"
    RAW = "raw"


class NodeKind(StrEnum):
    DOCUMENT = "document"
    ELEMENT = "element"
    TEXT = "text"
    COMMENT = "comment"
    CDATA = "cdata"
    PROCESSING_INSTRUCTION = "processing-instruction"
    DECLARATION = "declaration"
    RAW = "raw"


@dataclass(frozen=True, slots=True)
class SourceEnvelope:
    absolute_path: Path
    relative_path: str
    relative_path_bytes: bytes
    path_parts: tuple[str, ...]
    path_parts_bytes: tuple[bytes, ...]
    normalized_nfc_path: str
    sha256: str
    byte_size: int
    doc_group: str | None
    corp_folder: str | None
    corp_folder_nfc: str | None
    receipt_folder: str | None
    receipt_no: str | None
    file_name: str
    file_name_bytes: bytes
    file_role: str
    attachment_code: str | None
    detected_format: SourceFormat
    detected_encoding: str | None
    declared_encoding: str | None


@dataclass(frozen=True, slots=True)
class SourceArtifact:
    envelope: SourceEnvelope
    content: bytes


@dataclass(frozen=True, slots=True)
class AttributeSpan:
    name: str
    value: str | None
    quote: str | None
    start_byte: int
    end_byte: int
    name_start_byte: int
    name_end_byte: int
    value_start_byte: int | None
    value_end_byte: int | None


@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    start_byte: int
    end_byte: int
    name: str | None = None
    attributes: tuple[AttributeSpan, ...] = ()
    issues: tuple[str, ...] = ()

    def raw(self, source: bytes) -> bytes:
        return source[self.start_byte : self.end_byte]


@dataclass(frozen=True, slots=True)
class RecoveryEvent:
    code: str
    byte_offset: int
    node_id: int | None
    detail: str


@dataclass(frozen=True, slots=True)
class CstNode:
    node_id: int
    kind: NodeKind
    parent_id: int | None
    child_ids: tuple[int, ...]
    name: str | None
    start_byte: int
    end_byte: int
    start_token_index: int | None
    end_token_index: int | None
    implicitly_closed: bool = False


@dataclass(frozen=True, slots=True)
class ParsedArtifact:
    source: SourceArtifact
    tokens: tuple[Token, ...]
    nodes: tuple[CstNode, ...]
    recovery_events: tuple[RecoveryEvent, ...]

    def reconstruct(self) -> bytes:
        content = self.source.content
        return b"".join(token.raw(content) for token in self.tokens)

    def assert_lossless(self) -> None:
        content = self.source.content
        cursor = 0
        for index, token in enumerate(self.tokens):
            if token.start_byte != cursor:
                raise AssertionError(
                    f"token {index} begins at {token.start_byte}, expected {cursor}"
                )
            if token.end_byte < token.start_byte:
                raise AssertionError(f"token {index} has a negative span")
            cursor = token.end_byte
        if cursor != len(content):
            raise AssertionError(f"token coverage ends at {cursor}, expected {len(content)}")
        if self.reconstruct() != content:
            raise AssertionError("token reconstruction differs from source bytes")

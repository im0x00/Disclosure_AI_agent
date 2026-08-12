"""Evidence-linked semantic structural IR derived from a lossless CST."""

from __future__ import annotations

import base64
import html
import re
from collections.abc import Iterator, Mapping
from typing import Any

from disclosure_ai.data.adapters import EvidenceValue, describe
from disclosure_ai.data.models import CstNode, NodeKind, ParsedArtifact, Token

SCHEMA_VERSION = "semantic-structural-ir/v1"

_SECTION_RE = re.compile(r"SECTION-(?P<level>\d+)$", re.I)
_INTEGER_RE = re.compile(r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)$")
_DECIMAL_RE = re.compile(r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d+$")
_DISPLAY_DATE_RE = re.compile(r"^\d{4}[-./]\d{1,2}[-./]\d{1,2}$")
_DATE_KEYS = ("DT", "DATE", "DAY")
_SEMANTIC_ELEMENTS = {"TE", "TU", "EXTRACTION"}
_TITLE_ELEMENTS = {"TITLE", "COVER-TITLE"}
_PRESENTATION_ATTRIBUTES = {
    "ALIGN",
    "BORDER",
    "BORDERCOLOR",
    "BORDERCOLORDARK",
    "BORDERCOLORLIGHT",
    "CELLPADDING",
    "CELLSPACING",
    "HEIGHT",
    "STYLE",
    "VALIGN",
    "WIDTH",
}


def build_semantic_ir(
    parsed: ParsedArtifact, metadata: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Build a human-readable IR while retaining evidence back to immutable raw bytes."""

    parsed.assert_lossless()
    builder = _IrBuilder(parsed)
    return builder.build(dict(metadata or {}))


class _IrBuilder:
    def __init__(self, parsed: ParsedArtifact) -> None:
        self.parsed = parsed
        self.source = parsed.source.content
        self.nodes = parsed.nodes
        self.captured_text_nodes: set[int] = set()
        self.section_ids: dict[int, str] = {}
        self.table_ids: dict[int, str] = {}

    def build(self, metadata: dict[str, Any]) -> dict[str, Any]:
        descriptor = describe(self.parsed)
        sections = self._sections()
        fields = self._semantic_fields()
        blocks = self._blocks()
        if not blocks and self.parsed.source.envelope.detected_format.value not in {
            "dart-markup",
            "html",
        }:
            blocks.append(
                {
                    "id": "block-source-reference-0",
                    "ordinal": 0,
                    "kind": "source_reference",
                    "section_id": None,
                    "message": "No deterministic text structure is available for this artifact.",
                    "evidence": {"start_byte": 0, "end_byte": len(self.source)},
                }
            )
        self._capture_header_text()
        blocks.extend(self._unmapped_text_blocks(start_ordinal=len(blocks)))
        blocks.sort(key=lambda block: (int(block["evidence"]["start_byte"]), str(block["id"])))
        for ordinal, block in enumerate(blocks):
            block["ordinal"] = ordinal

        envelope = self.parsed.source.envelope
        return {
            "schema_version": SCHEMA_VERSION,
            "source": {
                "relative_path": envelope.relative_path,
                "relative_path_bytes_base64": _b64(envelope.relative_path_bytes),
                "path_parts": list(envelope.path_parts),
                "path_parts_bytes_base64": [_b64(part) for part in envelope.path_parts_bytes],
                "normalized_nfc_path": envelope.normalized_nfc_path,
                "sha256": envelope.sha256,
                "byte_size": envelope.byte_size,
                "detected_format": envelope.detected_format.value,
                "detected_encoding": envelope.detected_encoding,
                "declared_encoding": envelope.declared_encoding,
                "doc_group": envelope.doc_group,
                "corp_folder": envelope.corp_folder,
                "corp_folder_nfc": envelope.corp_folder_nfc,
                "receipt_folder": envelope.receipt_folder,
                "receipt_no": envelope.receipt_no,
                "file_name": envelope.file_name,
                "file_name_bytes_base64": _b64(envelope.file_name_bytes),
                "file_role": envelope.file_role,
                "attachment_code": envelope.attachment_code,
            },
            "projection_contract": {
                "authoritative_source": "corpus/raw",
                "source_bytes_verified_by_sha256": True,
                "all_extracted_source_values_are_evidence_linked": True,
                "projection_is_not_a_raw_source_replacement": True,
            },
            "document_metadata": metadata,
            "header": {
                "adapter": descriptor.adapter,
                "document_name": _evidence_value(descriptor.document_name),
                "document_code": _evidence_value(descriptor.document_code),
                "company_name": _evidence_value(descriptor.company_name),
                "company_code": _evidence_value(descriptor.company_code),
                "formula_version": _evidence_value(descriptor.formula_version),
                "schema_location": _evidence_value(descriptor.schema_location),
                "html_title": _evidence_value(descriptor.html_title),
            },
            "sections": sections,
            "semantic_fields": fields,
            "blocks": blocks,
            "diagnostics": {
                "lossless_source_verified": True,
                "parser_recovery_event_count": len(self.parsed.recovery_events),
                "parser_recovery_events": [
                    {
                        "code": event.code,
                        "byte_offset": event.byte_offset,
                        "node_id": event.node_id,
                        "detail": event.detail,
                    }
                    for event in self.parsed.recovery_events
                ],
                "non_whitespace_text_node_count": sum(
                    1 for node in self.nodes if self._meaningful_text_node(node)
                ),
                "captured_text_node_count": sum(
                    1
                    for node_id in self.captured_text_nodes
                    if self._meaningful_text_node(self.nodes[node_id])
                ),
                "all_non_whitespace_text_mapped": all(
                    not self._meaningful_text_node(node) or node.node_id in self.captured_text_nodes
                    for node in self.nodes
                ),
                "unmapped_text_block_count": sum(
                    1 for block in blocks if block["kind"] == "unmapped_text"
                ),
                "presentation_attribute_count_omitted_from_ir": sum(
                    1
                    for token in self.parsed.tokens
                    for attribute in token.attributes
                    if attribute.name.upper() in _PRESENTATION_ATTRIBUTES
                ),
            },
        }

    def _sections(self) -> list[dict[str, Any]]:
        section_nodes = [node for node in self.nodes if self._section_level(node) is not None]
        synthetic_root = False
        if not section_nodes:
            body = self._first_named_element("body")
            if body is not None:
                section_nodes = [body]
                synthetic_root = True
        for ordinal, node in enumerate(section_nodes):
            self.section_ids[node.node_id] = f"section-{ordinal}"

        sections: list[dict[str, Any]] = []
        for ordinal, node in enumerate(section_nodes):
            title_node = (
                self._first_named_element("title")
                if synthetic_root
                else self._first_section_title(node.node_id)
            )
            title = self._text(title_node.node_id) if title_node else None
            parent_node = self._nearest_ancestor_in(node.node_id, self.section_ids)
            sections.append(
                {
                    "id": self.section_ids[node.node_id],
                    "ordinal": ordinal,
                    "parent_section_id": (
                        self.section_ids.get(parent_node) if parent_node is not None else None
                    ),
                    "level": 0 if synthetic_root else self._section_level(node),
                    "source_element": node.name,
                    "title": title,
                    "title_evidence": self._evidence(title_node) if title_node else None,
                    "attributes": self._attributes(node),
                    "evidence": self._evidence(node),
                }
            )
        return sections

    def _semantic_fields(self) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = []
        for node in self.nodes:
            if (
                node.kind is not NodeKind.ELEMENT
                or (node.name or "").upper() not in _SEMANTIC_ELEMENTS
            ):
                continue
            attributes = self._attribute_map(node)
            key_type: str | None = None
            key: str | None = None
            for candidate in ("ACODE", "AUNIT"):
                if candidate in attributes:
                    key_type = candidate
                    key = attributes[candidate]
                    break
            if key is None and node.name != "EXTRACTION":
                continue
            text = self._text(node.node_id)
            machine_value = attributes.get("AUNITVALUE", text)
            fields.append(
                {
                    "id": f"field-{len(fields)}",
                    "ordinal": len(fields),
                    "section_id": self._section_id_for(node.node_id),
                    "element": node.name,
                    "key_type": key_type,
                    "key": key,
                    "text": text,
                    "machine_value": machine_value,
                    "value_type": _value_type(key, machine_value, display_text=text),
                    "attributes": self._attributes(node),
                    "evidence": self._evidence(node),
                }
            )
        return fields

    def _blocks(self) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        table_nodes = [
            node
            for node in self.nodes
            if node.kind is NodeKind.ELEMENT and (node.name or "").lower() == "table"
        ]
        for node in table_nodes:
            self.table_ids[node.node_id] = f"block-table-{len(self.table_ids)}"

        candidates = [
            node
            for node in self.nodes
            if node.kind is NodeKind.ELEMENT
            and (
                (node.name or "").lower() == "table"
                or self._is_heading(node)
                or (
                    (node.name or "").upper() == "P"
                    and self._ancestor_named(node.node_id, "TABLE") is None
                )
            )
        ]
        candidates.sort(key=lambda node: (node.start_byte, node.node_id))

        for node in candidates:
            if (node.name or "").lower() == "table":
                blocks.append(self._table_block(node, len(blocks)))
                continue
            text = self._text(node.node_id)
            if text:
                blocks.append(
                    {
                        "id": f"block-{len(blocks)}",
                        "ordinal": len(blocks),
                        "kind": "heading" if self._is_heading(node) else "paragraph",
                        "section_id": self._section_id_for(node.node_id),
                        "text": text,
                        "attributes": self._attributes(node),
                        "evidence": self._evidence(node),
                    }
                )
        return blocks

    def _table_block(self, table: CstNode, ordinal: int) -> dict[str, Any]:
        rows = self._table_rows(table.node_id)
        active_rowspans: dict[int, tuple[int, str]] = {}
        rendered_rows: list[dict[str, Any]] = []
        for row_index, row in enumerate(rows):
            inherited_labels = {
                column: label for column, (_, label) in active_rowspans.items() if label
            }
            cursor = 0
            rendered_cells: list[dict[str, Any]] = []
            new_rowspans: dict[int, tuple[int, str]] = {}
            preceding_labels: list[str] = []
            row_cells = self._row_cells(row.node_id, table.node_id)
            for cell_index, cell in enumerate(row_cells):
                while cursor in active_rowspans:
                    cursor += 1
                attributes = self._attribute_map(cell)
                rowspan = _positive_int(attributes.get("ROWSPAN"), default=1)
                colspan = _positive_int(attributes.get("COLSPAN"), default=1)
                text = self._text(cell.node_id)
                element = (cell.name or "").upper()
                semantic_key = attributes.get("ACODE") or attributes.get("AUNIT")
                role = _cell_role(
                    element,
                    semantic_key,
                    cell_index=cell_index,
                    cell_count=len(row_cells),
                )
                inherited = [
                    label
                    for column, label in sorted(inherited_labels.items())
                    if column < cursor and label
                ]
                context_labels = list(dict.fromkeys([*inherited, *preceding_labels]))
                rendered_cells.append(
                    {
                        "id": f"{self.table_ids[table.node_id]}-r{row_index}-c{cursor}",
                        "row_index": row_index,
                        "column_index": cursor,
                        "rowspan": rowspan,
                        "colspan": colspan,
                        "element": cell.name,
                        "role": role,
                        "semantic_key": semantic_key,
                        "machine_value": attributes.get("AUNITVALUE", text),
                        "value_type": _value_type(
                            semantic_key,
                            attributes.get("AUNITVALUE", text),
                            display_text=text,
                        ),
                        "text": text,
                        "context_labels": context_labels,
                        "attributes": self._attributes(cell),
                        "evidence": self._evidence(cell),
                    }
                )
                if role in {"label_or_text", "header"} and text:
                    preceding_labels.append(text)
                if rowspan > 1:
                    for column in range(cursor, cursor + colspan):
                        new_rowspans[column] = (rowspan - 1, text if role != "value" else "")
                cursor += colspan

            rendered_rows.append(
                {
                    "index": row_index,
                    "cells": rendered_cells,
                    "evidence": self._evidence(row),
                }
            )
            active_rowspans = {
                column: (remaining - 1, label)
                for column, (remaining, label) in active_rowspans.items()
                if remaining > 1
            }
            active_rowspans.update(new_rowspans)

        parent_table_node = self._ancestor_named(table.node_id, "TABLE")
        group_node = self._ancestor_named(table.node_id, "TABLE-GROUP")
        group_attributes = (
            self._attribute_map(self.nodes[group_node]) if group_node is not None else {}
        )
        return {
            "id": self.table_ids[table.node_id],
            "ordinal": ordinal,
            "kind": "table",
            "section_id": self._section_id_for(table.node_id),
            "parent_table_id": (
                self.table_ids.get(parent_table_node) if parent_table_node is not None else None
            ),
            "table_class": self._attribute_map(table).get("ACLASS"),
            "table_group_class": group_attributes.get("ACLASS"),
            "attributes": self._attributes(table),
            "rows": rendered_rows,
            "evidence": self._evidence(table),
        }

    def _unmapped_text_blocks(self, start_ordinal: int) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for node in self.nodes:
            if not self._meaningful_text_node(node) or node.node_id in self.captured_text_nodes:
                continue
            text = self._decode(self.source[node.start_byte : node.end_byte])
            text = _display_text([text])
            if not text:
                continue
            technical = (
                self._ancestor_named(node.node_id, "STYLE") is not None
                or self._ancestor_named(node.node_id, "SCRIPT") is not None
            )
            blocks.append(
                {
                    "id": f"block-unmapped-{len(blocks)}",
                    "ordinal": start_ordinal + len(blocks),
                    "kind": "unmapped_text",
                    "section_id": self._section_id_for(node.node_id),
                    "classification": "technical" if technical else "unmapped",
                    "text": text,
                    "evidence": self._evidence(node),
                }
            )
            self.captured_text_nodes.add(node.node_id)
        return blocks

    def _table_rows(self, table_id: int) -> list[CstNode]:
        return [
            node
            for node in self._descendants(table_id)
            if (node.name or "").lower() == "tr"
            and self._ancestor_named(node.node_id, "TABLE") == table_id
        ]

    def _row_cells(self, row_id: int, table_id: int) -> list[CstNode]:
        return [
            node
            for node in self._descendants(row_id)
            if (node.name or "").lower() in {"td", "th", "te", "tu"}
            and self._ancestor_named(node.node_id, "TR") == row_id
            and self._ancestor_named(node.node_id, "TABLE") == table_id
        ]

    def _first_section_title(self, section_id: int) -> CstNode | None:
        for node in self._descendants(section_id):
            owner = self._nearest_ancestor_in(node.node_id, self.section_ids)
            if owner == section_id and (node.name or "").upper() in _TITLE_ELEMENTS:
                return node
        return None

    def _first_named_element(self, name: str) -> CstNode | None:
        target = name.lower()
        return next(
            (
                node
                for node in self.nodes
                if node.kind is NodeKind.ELEMENT and (node.name or "").lower() == target
            ),
            None,
        )

    def _capture_header_text(self) -> None:
        names = {"DOCUMENT-NAME", "COMPANY-NAME", "FORMULA-VERSION", "TITLE"}
        for node in self.nodes:
            if node.kind is NodeKind.ELEMENT and (node.name or "").upper() in names:
                for descendant in self._descendants(node.node_id):
                    if descendant.kind is NodeKind.TEXT:
                        self.captured_text_nodes.add(descendant.node_id)

    def _is_heading(self, node: CstNode) -> bool:
        name = (node.name or "").lower()
        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return True
        classes = self._attribute_map(node).get("CLASS", "").lower().split()
        return "xforms_title" in classes

    def _text(self, node_id: int) -> str:
        pieces: list[str] = []
        for node in self._descendants(node_id, include_self=True):
            if node.kind is NodeKind.TEXT:
                raw = self.source[node.start_byte : node.end_byte]
                pieces.append(self._decode(raw))
                self.captured_text_nodes.add(node.node_id)
            elif node.kind is NodeKind.ELEMENT and (node.name or "").lower() in {"br", "p"}:
                pieces.append("\n")
        return _display_text(pieces)

    def _decode(self, value: bytes) -> str:
        encoding = self.parsed.source.envelope.detected_encoding or "utf-8"
        return value.decode(encoding, errors="replace")

    def _attributes(self, node: CstNode) -> list[dict[str, Any]]:
        token = self._start_token(node)
        if token is None:
            return []
        return [
            {
                "name": attribute.name,
                "value": attribute.value,
                "is_presentation": attribute.name.upper() in _PRESENTATION_ATTRIBUTES,
                "evidence": {
                    "start_byte": attribute.start_byte,
                    "end_byte": attribute.end_byte,
                },
            }
            for attribute in token.attributes
            if attribute.name.upper() not in _PRESENTATION_ATTRIBUTES
        ]

    def _attribute_map(self, node: CstNode) -> dict[str, str]:
        token = self._start_token(node)
        if token is None:
            return {}
        return {
            attribute.name.upper(): attribute.value
            for attribute in token.attributes
            if attribute.value is not None
        }

    def _start_token(self, node: CstNode) -> Token | None:
        if node.start_token_index is None:
            return None
        return self.parsed.tokens[node.start_token_index]

    def _section_id_for(self, node_id: int) -> str | None:
        if node_id in self.section_ids:
            return self.section_ids[node_id]
        ancestor = self._nearest_ancestor_in(node_id, self.section_ids)
        return self.section_ids.get(ancestor) if ancestor is not None else None

    def _nearest_ancestor_in(self, node_id: int, candidates: Mapping[int, Any]) -> int | None:
        parent = self.nodes[node_id].parent_id
        while parent is not None:
            if parent in candidates:
                return parent
            parent = self.nodes[parent].parent_id
        return None

    def _ancestor_named(self, node_id: int, name: str) -> int | None:
        target = name.lower()
        parent = self.nodes[node_id].parent_id
        while parent is not None:
            node = self.nodes[parent]
            if (node.name or "").lower() == target:
                return parent
            parent = node.parent_id
        return None

    def _descendants(self, node_id: int, *, include_self: bool = False) -> Iterator[CstNode]:
        pending = [node_id] if include_self else list(reversed(self.nodes[node_id].child_ids))
        while pending:
            current_id = pending.pop()
            current = self.nodes[current_id]
            yield current
            pending.extend(reversed(current.child_ids))

    def _section_level(self, node: CstNode) -> int | None:
        if node.kind is not NodeKind.ELEMENT or node.name is None:
            return None
        if node.name.upper() == "COVER":
            return 0
        match = _SECTION_RE.fullmatch(node.name)
        return int(match.group("level")) if match else None

    def _meaningful_text_node(self, node: CstNode) -> bool:
        if node.kind is not NodeKind.TEXT:
            return False
        raw = self.source[node.start_byte : node.end_byte]
        return bool(_display_text([self._decode(raw)]))

    @staticmethod
    def _evidence(node: CstNode) -> dict[str, int]:
        return {"start_byte": node.start_byte, "end_byte": node.end_byte}


def _display_text(pieces: list[str]) -> str:
    value = html.unescape("".join(pieces)).replace("\xa0", " ")
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _evidence_value(value: EvidenceValue | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "text": _display_text([value.text]),
        "evidence": {"start_byte": value.start_byte, "end_byte": value.end_byte},
    }


def _cell_role(
    element: str,
    semantic_key: str | None,
    *,
    cell_index: int,
    cell_count: int,
) -> str:
    if element == "TH":
        return "header"
    if element in {"TE", "TU"} or semantic_key is not None:
        return "value"
    if cell_count > 1 and cell_index == cell_count - 1:
        return "value"
    return "label_or_text"


def _value_type(key: str | None, value: str | None, *, display_text: str | None = None) -> str:
    if value is None or value == "":
        return "empty"
    stripped = value.strip()
    upper_key = (key or "").upper()
    digits = stripped.replace("-", "").replace("/", "").replace(".", "")
    date_display = (display_text or "").strip()
    if (
        len(digits) == 8
        and digits.isdigit()
        and (
            any(part in upper_key for part in _DATE_KEYS)
            or _DISPLAY_DATE_RE.fullmatch(date_display)
        )
    ):
        return "date"
    percentage = stripped[:-1].replace(",", "") if stripped.endswith("%") else ""
    if stripped.endswith("%") and (
        _INTEGER_RE.fullmatch(percentage) or _DECIMAL_RE.fullmatch(percentage)
    ):
        return "percentage"
    if _INTEGER_RE.fullmatch(stripped):
        return "integer"
    if _DECIMAL_RE.fullmatch(stripped):
        return "decimal"
    return "string"


def _positive_int(value: str | None, *, default: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass

from evidence.document_grain import (
    DocumentGrain,
    GrainKind,
    SemanticContext,
    SourceAddress,
)
from evidence.document_tree import ArtifactTree, DocumentTree, Node, NodeKind, SourceRange, Text

DEFAULT_MAX_ESTIMATED_TOKENS = 1_800
MIN_TABLE_SEGMENT_TOKENS = 64
MAX_REPEATED_TABLE_NOTE_TOKENS = 512
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[._%/+:-][A-Za-z0-9]+)*|[^\x00-\x7f\s]|[^\w\s]")
_RAW_PART_PATTERN = re.compile(
    r"&(?:#[0-9]+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);|\s+|[^\s&]+|&",
    re.DOTALL,
)
_UNIT_PATTERN = re.compile(r"\(?\s*단위\s*[:：]\s*[^)\n]{1,40}\)?")
_TABLE_CAPTION_PATTERN = re.compile(r"^(?:【.+】|\[.+\])$")
_TABLE_NOTE_PATTERN = re.compile(
    r"^(?:※|주\s*\d*\s*[:：.)]|\(?\s*주\s*\d+\s*\)?|\(?\s*\*+\d*\s*\)?)"
)
_TABLE_SIGN_LEGEND_PATTERN = re.compile(r"(?:△|▲|음\s*\(|부\s*\().{0,20}(?:값|표시)")
_NOTE_REFERENCE_PATTERN = re.compile(
    r"^(?P<marker>\(\s*\*+\d*\s*\)|\(\s*주\s*\d+\s*\)|주\s*\d+\s*\))"
)


@dataclass(frozen=True)
class _Heading:
    text: str
    source: SourceRange


@dataclass(frozen=True)
class _HeadingCandidate:
    heading: _Heading
    parents: tuple[_Heading, ...]


@dataclass(frozen=True)
class _CoreAtom:
    text: str
    source: SourceRange


@dataclass(frozen=True)
class _PlacedCell:
    cell: Node
    physical_ordinal: int
    start_column: int
    end_column: int


@dataclass(frozen=True)
class _TableCompilation:
    table: Node
    headings: tuple[_Heading, ...]
    unit: str | None
    caption: str | None
    context_ranges: tuple[SourceRange, ...]
    note_contexts: tuple[tuple[str, tuple[SourceRange, ...]], ...]
    start: int
    end: int


@dataclass(frozen=True)
class _DraftGrain:
    artifact_id: str
    source_path: str
    kind: GrainKind
    core_text: str
    headings: tuple[_Heading, ...]
    core_ranges: tuple[SourceRange, ...]
    context_ranges: tuple[SourceRange, ...] = ()
    caption: str | None = None
    unit: str | None = None
    table_headers: tuple[str, ...] = ()
    table_position: str | None = None
    notes: tuple[str, ...] = ()


def estimate_tokens(value: str) -> int:
    """Return a dependency-free, conservative token budget estimate."""

    return max(1, len(_TOKEN_PATTERN.findall(value)))


def _available_core_tokens(
    max_tokens: int,
    *,
    headings: tuple[_Heading, ...],
    caption: str | None = None,
    unit: str | None = None,
    table_headers: tuple[str, ...] = (),
    table_position: str | None = None,
    notes: tuple[str, ...] = (),
) -> int:
    context_parts: list[str] = []
    if headings:
        context_parts.append(f"Heading: {' > '.join(heading.text for heading in headings)}")
    if caption:
        context_parts.append(f"Caption: {caption}")
    if unit:
        context_parts.append(f"Unit: {unit}")
    if table_headers:
        context_parts.append(f"Table headers: {' | '.join(table_headers)}")
    if table_position:
        context_parts.append(f"Table position: {table_position}")
    if notes:
        context_parts.append(f"Notes: {' | '.join(notes)}")
    context_tokens = len(_TOKEN_PATTERN.findall("\n".join(context_parts)))
    return max(1, max_tokens - context_tokens)


def _normalized(value: str) -> str:
    return " ".join(html.unescape(value).split())


def _attribute(node: Node, name: str) -> str:
    lowered = name.lower()
    for attribute in reversed(node.attributes):
        if attribute.name.lower() == lowered:
            return attribute.value
    return ""


def _texts(node: Node) -> tuple[Text, ...]:
    result: list[Text] = []
    for item in node.content:
        if isinstance(item, Text):
            result.append(item)
        else:
            result.extend(_texts(item))
    return tuple(result)


def _node_text(node: Node) -> str:
    return " ".join(text.display_value for text in _texts(node) if text.display_value)


def _is_context_heading(node: Node) -> bool:
    if node.kind != NodeKind.HEADING:
        return False
    atoc = _attribute(node, "atoc").upper()
    return atoc != "N"


def _scope_id(artifact_id: str, headings: tuple[_Heading, ...]) -> str:
    parts = [artifact_id]
    for heading in headings:
        parts.extend(
            (
                heading.text,
                str(heading.source.start_byte),
                str(heading.source.end_byte),
            )
        )
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def _context(draft: _DraftGrain) -> SemanticContext:
    return SemanticContext(
        heading_path=tuple(heading.text for heading in draft.headings),
        caption=draft.caption,
        unit=draft.unit,
        table_headers=draft.table_headers,
        table_position=draft.table_position,
        notes=draft.notes,
    )


def _render(draft: _DraftGrain) -> str:
    lines: list[str] = []
    context = _context(draft)
    if context.heading_path:
        lines.append(f"Heading: {' > '.join(context.heading_path)}")
    if context.caption:
        lines.append(f"Caption: {context.caption}")
    if context.unit:
        lines.append(f"Unit: {context.unit}")
    if context.table_headers:
        lines.append("Table headers:")
        lines.extend(context.table_headers)
    if context.table_position:
        lines.append(f"Table position: {context.table_position}")
    if context.notes:
        lines.append("Notes:")
        lines.extend(context.notes)
    lines.append(draft.core_text)
    return "\n".join(lines)


def _source_subrange(text: Text, start_character: int, end_character: int) -> SourceRange:
    raw = text.raw_value
    start_byte = text.source.start_byte + len(raw[:start_character].encode("utf-8"))
    end_byte = text.source.start_byte + len(raw[:end_character].encode("utf-8"))
    return SourceRange(
        artifact_id=text.source.artifact_id,
        source_path=text.source.source_path,
        xpath=text.source.xpath,
        start_byte=start_byte,
        end_byte=end_byte,
    )


def _raw_parts(raw: str, max_tokens: int) -> tuple[tuple[int, int], ...]:
    result: list[tuple[int, int]] = []
    for match in _RAW_PART_PATTERN.finditer(raw):
        start, end = match.span()
        part = match.group()
        if estimate_tokens(_normalized(part)) <= max_tokens:
            result.append((start, end))
            continue
        result.extend((position, position + 1) for position in range(start, end))
    return tuple(result)


def _split_text(text: Text, max_tokens: int) -> tuple[_CoreAtom, ...]:
    if estimate_tokens(text.display_value) <= max_tokens:
        return (_CoreAtom(text=text.display_value, source=text.source),)

    atoms: list[_CoreAtom] = []
    chunk_start: int | None = None
    chunk_end: int | None = None
    for start, end in _raw_parts(text.raw_value, max_tokens):
        candidate_start = start if chunk_start is None else chunk_start
        candidate = _normalized(text.raw_value[candidate_start:end])
        if chunk_start is not None and estimate_tokens(candidate) > max_tokens:
            assert chunk_end is not None
            display = _normalized(text.raw_value[chunk_start:chunk_end])
            if display:
                atoms.append(
                    _CoreAtom(
                        text=display,
                        source=_source_subrange(text, chunk_start, chunk_end),
                    )
                )
            chunk_start = start
        elif chunk_start is None:
            chunk_start = start
        chunk_end = end

    if chunk_start is not None and chunk_end is not None:
        display = _normalized(text.raw_value[chunk_start:chunk_end])
        if display:
            atoms.append(
                _CoreAtom(
                    text=display,
                    source=_source_subrange(text, chunk_start, chunk_end),
                )
            )
    return tuple(atoms)


def _draft_from_atoms(
    atoms: tuple[_CoreAtom, ...],
    *,
    kind: GrainKind,
    headings: tuple[_Heading, ...],
    context_ranges: tuple[SourceRange, ...] = (),
    caption: str | None = None,
    unit: str | None = None,
    table_headers: tuple[str, ...] = (),
    table_position: str | None = None,
    notes: tuple[str, ...] = (),
) -> _DraftGrain:
    first = atoms[0]
    return _DraftGrain(
        artifact_id=first.source.artifact_id,
        source_path=first.source.source_path,
        kind=kind,
        core_text=" ".join(atom.text for atom in atoms),
        headings=headings,
        core_ranges=tuple(atom.source for atom in atoms),
        context_ranges=context_ranges,
        caption=caption,
        unit=unit,
        table_headers=table_headers,
        table_position=table_position,
        notes=notes,
    )


def _split_atoms(
    atoms: tuple[_CoreAtom, ...],
    *,
    kind: GrainKind,
    headings: tuple[_Heading, ...],
    max_tokens: int,
    context_ranges: tuple[SourceRange, ...] = (),
    caption: str | None = None,
    unit: str | None = None,
    table_headers: tuple[str, ...] = (),
    table_position: str | None = None,
    notes: tuple[str, ...] = (),
) -> tuple[_DraftGrain, ...]:
    result: list[_DraftGrain] = []
    current: list[_CoreAtom] = []
    for atom in atoms:
        candidate = _draft_from_atoms(
            tuple((*current, atom)),
            kind=kind,
            headings=headings,
            context_ranges=context_ranges,
            caption=caption,
            unit=unit,
            table_headers=table_headers,
            table_position=table_position,
            notes=notes,
        )
        if current and estimate_tokens(_render(candidate)) > max_tokens:
            result.append(
                _draft_from_atoms(
                    tuple(current),
                    kind=kind,
                    headings=headings,
                    context_ranges=context_ranges,
                    caption=caption,
                    unit=unit,
                    table_headers=table_headers,
                    table_position=table_position,
                    notes=notes,
                )
            )
            current = [atom]
        else:
            current.append(atom)
    if current:
        result.append(
            _draft_from_atoms(
                tuple(current),
                kind=kind,
                headings=headings,
                context_ranges=context_ranges,
                caption=caption,
                unit=unit,
                table_headers=table_headers,
                table_position=table_position,
                notes=notes,
            )
        )
    return tuple(result)


def _prose_drafts(
    texts: tuple[Text, ...],
    headings: tuple[_Heading, ...],
    max_tokens: int,
    *,
    kind: GrainKind = GrainKind.PROSE,
) -> tuple[_DraftGrain, ...]:
    core_tokens = _available_core_tokens(max_tokens, headings=headings)
    atoms = tuple(atom for text in texts for atom in _split_text(text, core_tokens))
    if not atoms:
        return ()
    return _split_atoms(
        atoms,
        kind=kind,
        headings=headings,
        max_tokens=max_tokens,
    )


def _table_rows(node: Node) -> tuple[tuple[Node, bool, int], ...]:
    result: list[tuple[Node, bool]] = []

    def visit(current: Node, in_head: bool = False) -> None:
        child_in_head = in_head or current.kind == NodeKind.TABLE_HEAD
        for item in current.content:
            if not isinstance(item, Node):
                continue
            if item.kind == NodeKind.TABLE_ROW:
                result.append((item, child_in_head))
            elif item.kind != NodeKind.TABLE:
                visit(item, child_in_head)

    visit(node)
    return tuple((row, in_head, ordinal) for ordinal, (row, in_head) in enumerate(result, start=1))


def _row_cells(row: Node) -> tuple[Node, ...]:
    result: list[Node] = []

    def visit(node: Node) -> None:
        for item in node.content:
            if not isinstance(item, Node):
                continue
            if item.kind == NodeKind.TABLE_CELL:
                result.append(item)
            elif item.kind not in {NodeKind.TABLE, NodeKind.TABLE_ROW}:
                visit(item)

    visit(row)
    return tuple(result)


def _render_cell(cell: Node, column: int) -> str:
    text = _node_text(cell).replace("|", r"\|") or "∅"
    spans: list[str] = []
    rowspan = _attribute(cell, "rowspan")
    colspan = _attribute(cell, "colspan")
    if rowspan:
        spans.append(f"rowspan={rowspan}")
    if colspan:
        spans.append(f"colspan={colspan}")
    span_text = f"[{','.join(spans)}]" if spans else ""
    return f"c{column}{span_text}={text}"


def _cell_prefix(cell: Node, column: int) -> str:
    rendered = _render_cell(cell, column)
    return rendered[: rendered.index("=") + 1]


def _render_row(row: Node, ordinal: int) -> str:
    cells = _row_cells(row)
    rendered_cells = tuple(_render_cell(cell, column) for column, cell in enumerate(cells, start=1))
    return f"r{ordinal}: {' | '.join(rendered_cells)}"


def _table_decoration(table: Node) -> tuple[str | None, str | None] | None:
    rows = _table_rows(table)
    if not rows:
        return None
    nonempty_cells = tuple(
        text
        for row, _, _ in rows
        for cell in _row_cells(row)
        if (text := _normalized(_node_text(cell)))
    )
    if not nonempty_cells:
        return None
    units = tuple(text for text in nonempty_cells if _UNIT_PATTERN.fullmatch(text) is not None)
    captions = tuple(
        text for text in nonempty_cells if _TABLE_CAPTION_PATTERN.fullmatch(text) is not None
    )
    if len(rows) == 1 and (
        len(units) <= 1 and len(captions) <= 1 and len(units) + len(captions) == len(nonempty_cells)
    ):
        return (units[0] if units else None, captions[0] if captions else None)

    has_header = any(
        in_head or any(cell.source_tag.lower() == "th" for cell in _row_cells(row))
        for row, in_head, _ in rows
    )
    cell_count = sum(len(_row_cells(row)) for row, _, _ in rows)
    text = _normalized(_node_text(table))
    unit_match = _UNIT_PATTERN.search(text)
    if (
        has_header
        or len(rows) > 5
        or cell_count > 9
        or _attribute(table, "border") not in {"", "0"}
        or unit_match is None
    ):
        return None
    caption = _normalized(f"{text[: unit_match.start()]} {text[unit_match.end() :]}")
    if caption and estimate_tokens(caption) > 256:
        return None
    return _normalized(unit_match.group()), caption or None


def _table_is_empty(table: Node) -> bool:
    rows = _table_rows(table)
    if not rows or _node_text(table):
        return False

    def has_image(node: Node) -> bool:
        return node.kind == NodeKind.IMAGE or any(
            has_image(item) for item in node.content if isinstance(item, Node)
        )

    return not has_image(table)


def _table_cell_ranges(table: Node) -> tuple[SourceRange, ...]:
    return tuple(cell.source for row, _, _ in _table_rows(table) for cell in _row_cells(row))


def _table_note(table: Node) -> str | None:
    text = _normalized(_node_text(table))
    rows = _table_rows(table)
    if not text or not rows:
        return None
    if any(
        in_head or any(cell.source_tag.lower() == "th" for cell in _row_cells(row))
        for row, in_head, _ in rows
    ):
        return None
    if (
        _TABLE_NOTE_PATTERN.match(text) is not None
        and estimate_tokens(text) <= MAX_REPEATED_TABLE_NOTE_TOKENS
    ) or (
        len(rows) <= 2
        and estimate_tokens(text) <= 256
        and _TABLE_SIGN_LEGEND_PATTERN.search(text) is not None
    ):
        return text
    return None


def _paragraph_note(paragraph: Node) -> str | None:
    if paragraph.kind != NodeKind.PARAGRAPH:
        return None
    text = _normalized(_node_text(paragraph))
    if not text:
        return None
    if (
        _TABLE_NOTE_PATTERN.match(text) is not None
        and estimate_tokens(text) <= MAX_REPEATED_TABLE_NOTE_TOKENS
    ) or (estimate_tokens(text) <= 256 and _TABLE_SIGN_LEGEND_PATTERN.search(text) is not None):
        return text
    return None


def _note_reference_marker(note: str) -> str | None:
    if "△" in note and _TABLE_SIGN_LEGEND_PATTERN.search(note) is not None:
        return "△"
    match = _NOTE_REFERENCE_PATTERN.match(note)
    if match is None:
        return None
    marker = re.sub(r"\s+", "", match.group("marker"))
    return marker


def _relevant_note_contexts(
    target_text: str,
    table_text: str,
    note_contexts: tuple[tuple[str, tuple[SourceRange, ...]], ...],
) -> tuple[tuple[str, tuple[SourceRange, ...]], ...]:
    compact_target = re.sub(r"\s+", "", target_text)
    compact_table = re.sub(r"\s+", "", table_text)
    return tuple(
        (note, ranges)
        for note, ranges in note_contexts
        if (marker := _note_reference_marker(note)) is None
        or marker not in compact_table
        or marker in compact_target
    )


def _positive_span(cell: Node, name: str) -> int:
    try:
        return max(1, int(_attribute(cell, name) or "1"))
    except ValueError:
        return 1


def _table_layout(
    rows: tuple[tuple[Node, bool, int], ...],
) -> dict[tuple[str, int, int], tuple[_PlacedCell, ...]]:
    occupied_until: dict[int, int] = {}
    result: dict[tuple[str, int, int], tuple[_PlacedCell, ...]] = {}
    for row_index, (row, _, _) in enumerate(rows, start=1):
        placed: list[_PlacedCell] = []
        next_column = 1
        for physical_ordinal, cell in enumerate(_row_cells(row), start=1):
            colspan = _positive_span(cell, "colspan")
            while any(
                occupied_until.get(column, 0) >= row_index
                for column in range(next_column, next_column + colspan)
            ):
                next_column += 1
            end_column = next_column + colspan - 1
            placed.append(
                _PlacedCell(
                    cell=cell,
                    physical_ordinal=physical_ordinal,
                    start_column=next_column,
                    end_column=end_column,
                )
            )
            occupied_through = row_index + _positive_span(cell, "rowspan") - 1
            for column in range(next_column, end_column + 1):
                occupied_until[column] = max(occupied_until.get(column, 0), occupied_through)
            next_column = end_column + 1
        result[(row.source.artifact_id, row.source.start_byte, row.source.end_byte)] = tuple(placed)
    return result


def _relevant_headers(
    header_rows: list[tuple[Node, int]],
    layout: dict[tuple[str, int, int], tuple[_PlacedCell, ...]],
    target: _PlacedCell,
) -> tuple[tuple[str, ...], tuple[SourceRange, ...]]:
    lines: list[str] = []
    ranges: list[SourceRange] = []
    for row, row_ordinal in header_rows:
        row_key = (row.source.artifact_id, row.source.start_byte, row.source.end_byte)
        selected = tuple(
            placed
            for placed in layout[row_key]
            if placed.start_column <= target.end_column and placed.end_column >= target.start_column
        )
        if not selected:
            continue
        lines.append(
            f"r{row_ordinal}: "
            + " | ".join(_render_cell(placed.cell, placed.physical_ordinal) for placed in selected)
        )
        ranges.extend(placed.cell.source for placed in selected)
    return tuple(lines), tuple(dict.fromkeys(ranges))


_TABLE_POSITION_PATTERN = re.compile(
    r"^row (?P<row>\d+), column(?:s)? (?P<start>\d+)(?:-(?P<end>\d+))?$"
)


def _table_position_span(value: str | None) -> tuple[int, int, int] | None:
    if value is None or (match := _TABLE_POSITION_PATTERN.fullmatch(value)) is None:
        return None
    start = int(match.group("start"))
    return int(match.group("row")), start, int(match.group("end") or start)


def _merge_table_segments(left: _DraftGrain, right: _DraftGrain) -> _DraftGrain:
    left_position = _table_position_span(left.table_position)
    right_position = _table_position_span(right.table_position)
    assert left_position is not None and right_position is not None
    row = left_position[0]
    start = min(left_position[1], right_position[1])
    end = max(left_position[2], right_position[2])
    position = f"row {row}, column {start}" if start == end else f"row {row}, columns {start}-{end}"
    return _DraftGrain(
        artifact_id=left.artifact_id,
        source_path=left.source_path,
        kind=GrainKind.TABLE,
        core_text=f"{left.core_text}\n{right.core_text}",
        headings=left.headings,
        core_ranges=(*left.core_ranges, *right.core_ranges),
        context_ranges=tuple(dict.fromkeys((*left.context_ranges, *right.context_ranges))),
        unit=left.unit,
        table_headers=tuple(dict.fromkeys((*left.table_headers, *right.table_headers))),
        table_position=position,
        notes=tuple(dict.fromkeys((*left.notes, *right.notes))),
    )


def _pack_tiny_table_segments(
    drafts: tuple[_DraftGrain, ...], max_tokens: int
) -> tuple[_DraftGrain, ...]:
    packed: list[_DraftGrain] = []
    for draft in drafts:
        if not packed:
            packed.append(draft)
            continue
        left = packed[-1]
        left_position = _table_position_span(left.table_position)
        right_position = _table_position_span(draft.table_position)
        compatible = (
            left.artifact_id == draft.artifact_id
            and left.headings == draft.headings
            and left.unit == draft.unit
            and left_position is not None
            and right_position is not None
            and left_position[0] == right_position[0]
            and right_position[1] <= left_position[2] + 1
        )
        if not compatible or (
            estimate_tokens(_render(left)) >= MIN_TABLE_SEGMENT_TOKENS
            and estimate_tokens(_render(draft)) >= MIN_TABLE_SEGMENT_TOKENS
        ):
            packed.append(draft)
            continue
        merged = _merge_table_segments(left, draft)
        if estimate_tokens(_render(merged)) <= max_tokens:
            packed[-1] = merged
        else:
            packed.append(draft)
    return tuple(packed)


def _table_drafts(
    table: Node,
    headings: tuple[_Heading, ...],
    max_tokens: int,
    *,
    inherited_unit: str | None = None,
    inherited_caption: str | None = None,
    inherited_context_ranges: tuple[SourceRange, ...] = (),
    inherited_note_contexts: tuple[tuple[str, tuple[SourceRange, ...]], ...] = (),
) -> tuple[_DraftGrain, ...]:
    rows = _table_rows(table)
    if not rows:
        return _prose_drafts(_texts(table), headings, max_tokens, kind=GrainKind.TABLE)

    header_rows: list[tuple[Node, int]] = []
    data_rows: list[tuple[Node, int]] = []
    for row, in_head, ordinal in rows:
        cells = _row_cells(row)
        is_header = in_head or any(cell.source_tag.lower() == "th" for cell in cells)
        (header_rows if is_header else data_rows).append((row, ordinal))
    if not data_rows:
        data_rows = header_rows
        header_rows = []

    table_headers = tuple(_render_row(row, ordinal) for row, ordinal in header_rows)
    header_ranges = tuple(cell.source for row, _ in header_rows for cell in _row_cells(row))
    layout = _table_layout(rows)
    table_text = _node_text(table)
    unit_match = _UNIT_PATTERN.search(table_text)
    unit = _normalized(unit_match.group()) if unit_match is not None else inherited_unit

    atoms: list[_CoreAtom] = []
    for row, ordinal in data_rows:
        atoms.append(
            _CoreAtom(
                text=_render_row(row, ordinal),
                source=row.source,
            )
        )
    if not atoms:
        return ()

    result: list[_DraftGrain] = []
    for atom in atoms:
        row_note_contexts = _relevant_note_contexts(
            f"{atom.text} {' '.join(table_headers)}",
            table_text,
            inherited_note_contexts,
        )
        row_notes = tuple(note for note, _ in row_note_contexts)
        row_context_ranges = tuple(
            dict.fromkeys(
                (
                    *header_ranges,
                    *inherited_context_ranges,
                    *(source_range for _, ranges in row_note_contexts for source_range in ranges),
                )
            )
        )
        probe = _draft_from_atoms(
            (atom,),
            kind=GrainKind.TABLE,
            headings=headings,
            context_ranges=row_context_ranges,
            caption=inherited_caption,
            unit=unit,
            table_headers=table_headers,
            notes=row_notes,
        )
        if estimate_tokens(_render(probe)) <= max_tokens:
            result.append(probe)
            continue

        row, row_ordinal = next(
            (row, ordinal) for row, ordinal in data_rows if row.source == atom.source
        )
        cells = _row_cells(row)
        cell_drafts: list[_DraftGrain] = []
        for index, cell in enumerate(cells):
            table_position = f"row {row_ordinal}, column {index + 1}"
            row_key = (row.source.artifact_id, row.source.start_byte, row.source.end_byte)
            target = layout[row_key][index]
            cell_headers, cell_header_ranges = _relevant_headers(header_rows, layout, target)
            cell_note_contexts = _relevant_note_contexts(
                f"{_node_text(cell)} {' '.join(cell_headers)}",
                table_text,
                inherited_note_contexts,
            )
            cell_notes = tuple(note for note, _ in cell_note_contexts)
            cell_prefix = f"r{row_ordinal}: {_cell_prefix(cell, index + 1)}"
            core_tokens = _available_core_tokens(
                max_tokens,
                headings=headings,
                caption=inherited_caption,
                unit=unit,
                table_headers=cell_headers,
                table_position=table_position,
                notes=cell_notes,
            )
            core_tokens = max(1, core_tokens - estimate_tokens(cell_prefix))
            cell_atoms = tuple(
                part for text in _texts(cell) for part in _split_text(text, core_tokens)
            )
            if cell_atoms:
                cell_atoms = tuple(
                    _CoreAtom(
                        text=f"{cell_prefix}{atom.text}",
                        source=atom.source,
                    )
                    for atom in cell_atoms
                )
            else:
                cell_atoms = (
                    _CoreAtom(
                        text=f"r{row_ordinal}: {_render_cell(cell, index + 1)}",
                        source=cell.source,
                    ),
                )
            cell_drafts.extend(
                _split_atoms(
                    cell_atoms,
                    kind=GrainKind.TABLE,
                    headings=headings,
                    max_tokens=max_tokens,
                    context_ranges=tuple(
                        dict.fromkeys(
                            (
                                *cell_header_ranges,
                                *inherited_context_ranges,
                                *(
                                    source_range
                                    for _, ranges in cell_note_contexts
                                    for source_range in ranges
                                ),
                            )
                        )
                    ),
                    caption=inherited_caption,
                    unit=unit,
                    table_headers=cell_headers,
                    table_position=table_position,
                    notes=cell_notes,
                )
            )
        result.extend(_pack_tiny_table_segments(tuple(cell_drafts), max_tokens))
    return _pack_drafts(tuple(result), max_tokens)


def _image_drafts(
    image: Node,
    headings: tuple[_Heading, ...],
) -> tuple[_DraftGrain, ...]:
    label = _node_text(image)
    if not label:
        label = "Image"
    return (
        _DraftGrain(
            artifact_id=image.source.artifact_id,
            source_path=image.source.source_path,
            kind=GrainKind.IMAGE,
            core_text=label,
            headings=headings,
            core_ranges=(image.source,),
        ),
    )


def _collect_artifact_drafts(
    artifact: ArtifactTree,
    max_tokens: int,
) -> tuple[_DraftGrain, ...]:
    result: list[_DraftGrain] = []
    heading_candidates: list[_HeadingCandidate] = []

    def visit(
        node: Node,
        inherited: tuple[_Heading, ...],
    ) -> _TableCompilation | None:
        active = list(inherited)
        local_heading_index: int | None = None
        direct_texts: list[Text] = []
        pending_table_decorations: list[
            tuple[Node, tuple[_Heading, ...], str | None, str | None, str | None]
        ] = []
        bridged_notes: list[tuple[str, tuple[SourceRange, ...], str]] = []
        last_table: _TableCompilation | None = None

        def flush_direct_texts() -> None:
            nonlocal last_table
            if direct_texts:
                result.extend(
                    _prose_drafts(
                        tuple(direct_texts),
                        tuple(active),
                        max_tokens,
                    )
                )
                direct_texts.clear()
                last_table = None
                bridged_notes.clear()

        def flush_table_decorations() -> None:
            nonlocal last_table
            for table, headings, _, _, _ in pending_table_decorations:
                result.extend(_table_drafts(table, headings, max_tokens))
            pending_table_decorations.clear()
            bridged_notes.clear()
            last_table = None

        def compile_table(
            table: Node,
            headings: tuple[_Heading, ...],
            *,
            unit: str | None,
            caption: str | None,
            context_ranges: tuple[SourceRange, ...],
            note_contexts: tuple[tuple[str, tuple[SourceRange, ...]], ...],
        ) -> _TableCompilation | None:
            table_drafts = _table_drafts(
                table,
                headings,
                max_tokens,
                inherited_unit=unit,
                inherited_caption=caption,
                inherited_context_ranges=context_ranges,
                inherited_note_contexts=note_contexts,
            )
            if not table_drafts:
                return None
            start = len(result)
            result.extend(table_drafts)
            return _TableCompilation(
                table=table,
                headings=headings,
                unit=unit,
                caption=caption,
                context_ranges=context_ranges,
                note_contexts=note_contexts,
                start=start,
                end=len(result),
            )

        def add_note_to_last_table(
            note: str,
            note_ranges: tuple[SourceRange, ...],
        ) -> None:
            nonlocal last_table
            assert last_table is not None
            note_contexts = tuple(dict.fromkeys((*last_table.note_contexts, (note, note_ranges))))
            table_drafts = _table_drafts(
                last_table.table,
                last_table.headings,
                max_tokens,
                inherited_unit=last_table.unit,
                inherited_caption=last_table.caption,
                inherited_context_ranges=last_table.context_ranges,
                inherited_note_contexts=note_contexts,
            )
            result[last_table.start : last_table.end] = table_drafts
            last_table = _TableCompilation(
                table=last_table.table,
                headings=last_table.headings,
                unit=last_table.unit,
                caption=last_table.caption,
                context_ranges=last_table.context_ranges,
                note_contexts=note_contexts,
                start=last_table.start,
                end=last_table.start + len(table_drafts),
            )

        for item in node.content:
            if isinstance(item, Text):
                flush_table_decorations()
                if node.kind != NodeKind.METADATA:
                    direct_texts.append(item)
                continue
            flush_direct_texts()
            if _is_context_heading(item):
                flush_table_decorations()
                last_table = None
                heading_text = _node_text(item)
                if heading_text:
                    heading = _Heading(
                        text=heading_text,
                        source=item.source,
                    )
                    if local_heading_index is None:
                        heading_candidates.append(
                            _HeadingCandidate(heading=heading, parents=tuple(active))
                        )
                        local_heading_index = len(active)
                        active.append(heading)
                    else:
                        heading_candidates.append(
                            _HeadingCandidate(
                                heading=heading,
                                parents=tuple(active[:local_heading_index]),
                            )
                        )
                        active[local_heading_index] = heading
                        del active[local_heading_index + 1 :]
                continue
            headings = tuple(active)
            paragraph_note = _paragraph_note(item)
            if (
                paragraph_note is not None
                and last_table is not None
                and not pending_table_decorations
            ):
                note_ranges = tuple(text.source for text in _texts(item))
                add_note_to_last_table(paragraph_note, note_ranges)
                if (marker := _note_reference_marker(paragraph_note)) is not None:
                    bridged_notes.append((paragraph_note, note_ranges, marker))
                continue

            if item.kind == NodeKind.TABLE:
                if _table_is_empty(item):
                    continue

                note = _table_note(item)
                if note is not None:
                    note_ranges = _table_cell_ranges(item)
                    if last_table is not None and not pending_table_decorations:
                        add_note_to_last_table(note, note_ranges)
                        if (marker := _note_reference_marker(note)) is not None:
                            bridged_notes.append((note, note_ranges, marker))
                    else:
                        pending_table_decorations.append((item, headings, None, None, note))
                        last_table = None
                    continue

                decoration = _table_decoration(item)
                if decoration is not None:
                    last_table = None
                    unit, caption = decoration
                    has_same_role = any(
                        (unit is not None and existing_unit is not None)
                        or (caption is not None and existing_caption is not None)
                        for _, _, existing_unit, existing_caption, _ in pending_table_decorations
                    )
                    if has_same_role:
                        flush_table_decorations()
                    pending_table_decorations.append((item, headings, unit, caption, None))
                    continue

                inherited_unit = next(
                    (
                        unit
                        for _, _, unit, _, _ in reversed(pending_table_decorations)
                        if unit is not None
                    ),
                    None,
                )
                inherited_caption = next(
                    (
                        caption
                        for _, _, _, caption, _ in reversed(pending_table_decorations)
                        if caption is not None
                    ),
                    None,
                )
                pending_note_contexts = tuple(
                    (note, _table_cell_ranges(table))
                    for table, _, _, _, note in pending_table_decorations
                    if note is not None
                )
                normalized_table_text = re.sub(r"\s+", "", _node_text(item))
                matched_bridges = tuple(
                    (note, ranges)
                    for note, ranges, marker in bridged_notes
                    if marker in normalized_table_text
                )
                inherited_note_contexts = tuple(
                    dict.fromkeys((*pending_note_contexts, *matched_bridges))
                )
                inherited_ranges = tuple(
                    source_range
                    for table, _, _, _, note in pending_table_decorations
                    if note is None
                    for source_range in _table_cell_ranges(table)
                )
                last_table = compile_table(
                    item,
                    headings,
                    unit=inherited_unit,
                    caption=inherited_caption,
                    context_ranges=inherited_ranges,
                    note_contexts=inherited_note_contexts,
                )
                pending_table_decorations.clear()
                bridged_notes.clear()
                continue

            if item.kind in {NodeKind.PAGE_BREAK, NodeKind.LINE_BREAK} or (
                item.kind == NodeKind.PARAGRAPH and not _texts(item)
            ):
                continue

            flush_table_decorations()
            last_table = None
            if item.kind == NodeKind.PARAGRAPH:
                result.extend(
                    _prose_drafts(
                        _texts(item),
                        headings,
                        max_tokens,
                    )
                )
            elif item.kind == NodeKind.IMAGE:
                result.extend(_image_drafts(item, headings))
            elif item.kind == NodeKind.CAPTION:
                result.extend(
                    _prose_drafts(
                        _texts(item),
                        headings,
                        max_tokens,
                        kind=GrainKind.IMAGE,
                    )
                )
            else:
                last_table = visit(item, headings)
        flush_direct_texts()
        if pending_table_decorations:
            flush_table_decorations()
        return last_table

    visit(artifact.root, ())
    covered_heading_ranges = {
        (
            heading.source.artifact_id,
            heading.source.start_byte,
            heading.source.end_byte,
        )
        for draft in result
        for heading in draft.headings
    }
    for candidate in heading_candidates:
        heading = candidate.heading
        range_key = (
            heading.source.artifact_id,
            heading.source.start_byte,
            heading.source.end_byte,
        )
        if range_key in covered_heading_ranges:
            continue
        result.append(
            _DraftGrain(
                artifact_id=heading.source.artifact_id,
                source_path=heading.source.source_path,
                kind=GrainKind.PROSE,
                core_text=heading.text,
                headings=candidate.parents,
                core_ranges=(heading.source,),
            )
        )
    result.sort(key=lambda draft: draft.core_ranges[0].start_byte)
    if not result:
        title = artifact.title.display_value if artifact.title is not None else artifact.source_path
        result.append(
            _DraftGrain(
                artifact_id=artifact.artifact_id,
                source_path=artifact.source_path,
                kind=GrainKind.DOCUMENT,
                core_text=title,
                headings=(),
                core_ranges=(artifact.root.source,),
            )
        )
    return _pack_drafts(tuple(result), max_tokens)


def _same_pack_scope(left: _DraftGrain, right: _DraftGrain) -> bool:
    return (
        left.artifact_id == right.artifact_id
        and left.kind == right.kind
        and _scope_id(left.artifact_id, left.headings)
        == _scope_id(right.artifact_id, right.headings)
        and left.caption == right.caption
        and left.unit == right.unit
        and left.table_headers == right.table_headers
        and left.table_position == right.table_position
        and left.notes == right.notes
    )


def _merge(left: _DraftGrain, right: _DraftGrain) -> _DraftGrain:
    return _DraftGrain(
        artifact_id=left.artifact_id,
        source_path=left.source_path,
        kind=left.kind,
        core_text=f"{left.core_text}\n{right.core_text}",
        headings=left.headings,
        core_ranges=(*left.core_ranges, *right.core_ranges),
        context_ranges=tuple(dict.fromkeys((*left.context_ranges, *right.context_ranges))),
        caption=left.caption,
        unit=left.unit,
        table_headers=left.table_headers,
        table_position=left.table_position,
        notes=left.notes,
    )


def _pack_drafts(drafts: tuple[_DraftGrain, ...], max_tokens: int) -> tuple[_DraftGrain, ...]:
    packed: list[_DraftGrain] = []
    for draft in drafts:
        if not packed or not _same_pack_scope(packed[-1], draft):
            packed.append(draft)
            continue
        merged = _merge(packed[-1], draft)
        if estimate_tokens(_render(merged)) <= max_tokens:
            packed[-1] = merged
        else:
            packed.append(draft)
    return tuple(packed)


def _grain_id(doc_id: str, draft: _DraftGrain) -> str:
    parts = [doc_id, draft.artifact_id, draft.kind]
    for source_range in draft.core_ranges:
        parts.extend((str(source_range.start_byte), str(source_range.end_byte)))
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def compile_document_grains(
    tree: DocumentTree,
    *,
    max_estimated_tokens: int = DEFAULT_MAX_ESTIMATED_TOKENS,
) -> tuple[DocumentGrain, ...]:
    if max_estimated_tokens < 1:
        raise ValueError("max_estimated_tokens must be at least 1")

    drafts = tuple(
        draft
        for artifact in tree.artifacts
        for draft in _collect_artifact_drafts(artifact, max_estimated_tokens)
    )
    grain_ids = tuple(_grain_id(tree.doc_id, draft) for draft in drafts)
    grains: list[DocumentGrain] = []
    for ordinal, (draft, grain_id) in enumerate(zip(drafts, grain_ids, strict=True)):
        rendered = _render(draft)
        estimated_tokens = estimate_tokens(rendered)
        if estimated_tokens > max_estimated_tokens:
            raise ValueError(
                f"grain exceeds token budget: doc_id={tree.doc_id} "
                f"artifact_id={draft.artifact_id} ordinal={ordinal} "
                f"estimated_tokens={estimated_tokens} max={max_estimated_tokens}"
            )
        heading_ranges = tuple(heading.source for heading in draft.headings)
        context_ranges = tuple(dict.fromkeys((*heading_ranges, *draft.context_ranges)))
        grains.append(
            DocumentGrain(
                grain_id=grain_id,
                doc_id=tree.doc_id,
                kind=draft.kind,
                core_text=draft.core_text,
                rendered_text=rendered,
                estimated_tokens=estimated_tokens,
                context=_context(draft),
                source=SourceAddress(
                    artifact_id=draft.artifact_id,
                    source_path=draft.source_path,
                    ordinal=ordinal,
                    scope_id=_scope_id(draft.artifact_id, draft.headings),
                    core_ranges=draft.core_ranges,
                    context_ranges=context_ranges,
                ),
                previous_grain_id=grain_ids[ordinal - 1] if ordinal > 0 else None,
                next_grain_id=(grain_ids[ordinal + 1] if ordinal + 1 < len(grain_ids) else None),
            )
        )
    return tuple(grains)

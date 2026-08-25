from __future__ import annotations

import argparse
import hashlib
import math
import os
import re
import sys
import time
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from evidence.compiler import compile_document_tree
from evidence.document_grain import DocumentGrain, GrainKind
from evidence.document_tree import ArtifactTree, DocumentTree, Node, NodeKind, SourceRange, Text
from evidence.grain_compiler import (
    DEFAULT_MAX_ESTIMATED_TOKENS,
    MAX_REPEATED_TABLE_NOTE_TOKENS,
    compile_document_grains,
    estimate_tokens,
)
from evidence.loader import index_document_directories, nfc, read_documents

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INTERRUPTED_RETRIES = 5
_TABLE_POSITION_PATTERN = re.compile(
    r"^row (?P<row>\d+), column(?:s)? (?P<start>\d+)(?:-(?P<end>\d+))?$"
)
_UNIT_ONLY_PATTERN = re.compile(r"\(?\s*단위\s*[:：]\s*[^)\n]{1,40}\)?")
_TABLE_CAPTION_PATTERN = re.compile(r"^(?:【.+】|\[.+\])$")
_TABLE_NOTE_PATTERN = re.compile(
    r"^(?:※|주\s*\d*\s*[:：.)]|\(?\s*주\s*\d+\s*\)?|\(?\s*\*+\d*\s*\)?)"
)
_TABLE_SIGN_LEGEND_PATTERN = re.compile(r"(?:△|▲|음\s*\(|부\s*\().{0,20}(?:값|표시)")


@dataclass(frozen=True)
class GrainValidationTask:
    position: int
    doc_id: str
    file_path: str
    file_count: int
    directory: Path
    corpus_root: Path
    max_estimated_tokens: int


@dataclass(frozen=True)
class _ExpectedCell:
    artifact_id: str
    row_range: SourceRange
    cell_range: SourceRange
    row_ordinal: int
    column_ordinal: int
    header: bool
    empty: bool


@dataclass
class _Expectations:
    core_ranges: list[SourceRange] = field(default_factory=list)
    context_ranges: list[SourceRange] = field(default_factory=list)
    cells: list[_ExpectedCell] = field(default_factory=list)


@dataclass(frozen=True)
class DocumentGrainValidationResult:
    position: int
    grains: int = 0
    core_ranges: int = 0
    context_ranges: int = 0
    max_estimated_tokens: int = 0
    estimated_token_histogram: tuple[int, ...] = ()
    grain_kind_counts: tuple[tuple[str, int], ...] = ()
    failures: tuple[GrainValidationFailure, ...] = ()


class GrainValidationFailure(BaseModel):
    model_config = ConfigDict(frozen=True)

    doc_id: str | None
    file_path: str | None
    error_type: str
    message: str


class CorpusGrainValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    passed: bool
    manifest_documents: int = Field(ge=0)
    filesystem_documents: int = Field(ge=0)
    checked_documents: int = Field(ge=0)
    compiled_grains: int = Field(ge=0)
    validated_core_ranges: int = Field(ge=0)
    validated_context_ranges: int = Field(ge=0)
    max_estimated_tokens: int = Field(ge=0)
    average_estimated_tokens: float = Field(ge=0)
    estimated_token_p50: int = Field(ge=0)
    estimated_token_p90: int = Field(ge=0)
    estimated_token_p99: int = Field(ge=0)
    tiny_grains_under_64: int = Field(ge=0)
    tiny_grain_ratio: float = Field(ge=0, le=1)
    token_bucket_counts: dict[str, int]
    grain_kind_counts: dict[str, int]
    elapsed_seconds: float = Field(ge=0)
    failures: tuple[GrainValidationFailure, ...] = ()


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


def _is_context_heading(node: Node) -> bool:
    return node.kind == NodeKind.HEADING and _attribute(node, "atoc").upper() != "N"


def _row_cells(row: Node) -> tuple[Node, ...]:
    result: list[Node] = []

    def visit(current: Node) -> None:
        for item in current.content:
            if not isinstance(item, Node):
                continue
            if item.kind == NodeKind.TABLE_CELL:
                result.append(item)
            elif item.kind not in {NodeKind.TABLE, NodeKind.TABLE_ROW}:
                visit(item)

    visit(row)
    return tuple(result)


def _table_rows(table: Node) -> tuple[tuple[Node, bool, int], ...]:
    rows: list[tuple[Node, bool]] = []

    def visit(current: Node, in_head: bool = False) -> None:
        child_in_head = in_head or current.kind == NodeKind.TABLE_HEAD
        for item in current.content:
            if not isinstance(item, Node):
                continue
            if item.kind == NodeKind.TABLE_ROW:
                rows.append((item, child_in_head))
            elif item.kind != NodeKind.TABLE:
                visit(item, child_in_head)

    visit(table)
    return tuple((row, in_head, ordinal) for ordinal, (row, in_head) in enumerate(rows, start=1))


def _is_table_decoration(table: Node) -> bool:
    rows = _table_rows(table)
    table_text = " ".join(value.display_value for value in _texts(table)).strip()
    has_header = any(
        in_head or any(cell.source_tag.lower() == "th" for cell in _row_cells(row))
        for row, in_head, _ in rows
    )
    if (
        rows
        and not has_header
        and (
            (
                _TABLE_NOTE_PATTERN.match(table_text) is not None
                and estimate_tokens(table_text) <= MAX_REPEATED_TABLE_NOTE_TOKENS
            )
            or (
                len(rows) <= 2
                and estimate_tokens(table_text) <= 256
                and _TABLE_SIGN_LEGEND_PATTERN.search(table_text) is not None
            )
        )
    ):
        return True
    if not rows:
        return False
    nonempty_cells = tuple(
        text
        for row, _, _ in rows
        for cell in _row_cells(row)
        if (text := " ".join(value.display_value for value in _texts(cell)).strip())
    )
    if not nonempty_cells:
        return False
    recognized = sum(
        1
        for text in nonempty_cells
        if _UNIT_ONLY_PATTERN.fullmatch(text) is not None
        or _TABLE_CAPTION_PATTERN.fullmatch(text) is not None
    )
    unit_count = sum(_UNIT_ONLY_PATTERN.fullmatch(text) is not None for text in nonempty_cells)
    caption_count = sum(
        _TABLE_CAPTION_PATTERN.fullmatch(text) is not None for text in nonempty_cells
    )
    if (
        len(rows) == 1
        and recognized == len(nonempty_cells)
        and unit_count <= 1
        and caption_count <= 1
    ):
        return True
    cell_count = sum(len(_row_cells(row)) for row, _, _ in rows)
    unit_match = _UNIT_ONLY_PATTERN.search(table_text)
    caption_text = (
        f"{table_text[: unit_match.start()]} {table_text[unit_match.end() :]}"
        if unit_match is not None
        else ""
    )
    caption = " ".join(caption_text.split())
    return (
        not has_header
        and len(rows) <= 5
        and cell_count <= 9
        and _attribute(table, "border") in {"", "0"}
        and unit_match is not None
        and estimate_tokens(caption) <= 256
    )


def _is_empty_layout_table(table: Node) -> bool:
    if not _table_rows(table) or _texts(table):
        return False

    def has_image(node: Node) -> bool:
        return node.kind == NodeKind.IMAGE or any(
            has_image(item) for item in node.content if isinstance(item, Node)
        )

    return not has_image(table)


def _is_paragraph_note(node: Node) -> bool:
    if node.kind != NodeKind.PARAGRAPH:
        return False
    text = " ".join(value.display_value for value in _texts(node)).strip()
    return bool(text) and (
        (
            _TABLE_NOTE_PATTERN.match(text) is not None
            and estimate_tokens(text) <= MAX_REPEATED_TABLE_NOTE_TOKENS
        )
        or (estimate_tokens(text) <= 256 and _TABLE_SIGN_LEGEND_PATTERN.search(text) is not None)
    )


def _table_expectations(table: Node, expected: _Expectations) -> None:
    if _is_empty_layout_table(table):
        return
    if _is_table_decoration(table):
        expected.context_ranges.extend(
            cell.source for row, _, _ in _table_rows(table) for cell in _row_cells(row)
        )
        return

    rows = _table_rows(table)
    classified: list[tuple[Node, bool, int]] = []
    has_data = False
    for row, in_head, ordinal in rows:
        cells = _row_cells(row)
        header = in_head or any(cell.source_tag.lower() == "th" for cell in cells)
        classified.append((row, header, ordinal))
        has_data = has_data or not header

    for row, header, row_ordinal in classified:
        effective_header = header and has_data
        cells = _row_cells(row)
        for column_ordinal, cell in enumerate(cells, start=1):
            cell_texts = _texts(cell)
            if effective_header:
                expected.context_ranges.append(cell.source)
            elif cell_texts:
                expected.core_ranges.extend(text.source for text in cell_texts)
            else:
                expected.core_ranges.append(cell.source)
            expected.cells.append(
                _ExpectedCell(
                    artifact_id=table.source.artifact_id,
                    row_range=row.source,
                    cell_range=cell.source,
                    row_ordinal=row_ordinal,
                    column_ordinal=column_ordinal,
                    header=effective_header,
                    empty=not any(text.display_value for text in cell_texts),
                )
            )

    def collect_outside_rows(node: Node, inside_row: bool = False) -> None:
        current_inside_row = inside_row or node.kind == NodeKind.TABLE_ROW
        for item in node.content:
            if isinstance(item, Text):
                if not current_inside_row:
                    expected.core_ranges.append(item.source)
            elif item.kind != NodeKind.TABLE:
                collect_outside_rows(item, current_inside_row)

    collect_outside_rows(table)


def _artifact_expectations(artifact: ArtifactTree) -> _Expectations:
    expected = _Expectations()

    def visit(node: Node) -> bool:
        last_was_main_table = False
        for item in node.content:
            if isinstance(item, Text):
                if node.kind != NodeKind.METADATA:
                    expected.core_ranges.append(item.source)
                    last_was_main_table = False
                continue

            if item.kind == NodeKind.TABLE:
                empty = _is_empty_layout_table(item)
                decoration = _is_table_decoration(item)
                _table_expectations(item, expected)
                if empty:
                    continue
                if decoration:
                    table_text = " ".join(value.display_value for value in _texts(item)).strip()
                    is_note = (
                        _TABLE_NOTE_PATTERN.match(table_text) is not None
                        and estimate_tokens(table_text) <= MAX_REPEATED_TABLE_NOTE_TOKENS
                    ) or (
                        estimate_tokens(table_text) <= 256
                        and _TABLE_SIGN_LEGEND_PATTERN.search(table_text) is not None
                    )
                    last_was_main_table = last_was_main_table and is_note
                else:
                    last_was_main_table = True
                continue

            if _is_context_heading(item):
                if _texts(item):
                    expected.context_ranges.append(item.source)
                last_was_main_table = False
                continue
            if item.kind == NodeKind.IMAGE:
                expected.core_ranges.append(item.source)
                last_was_main_table = False
                continue
            if item.kind in {NodeKind.PAGE_BREAK, NodeKind.LINE_BREAK} or (
                item.kind == NodeKind.PARAGRAPH and not _texts(item)
            ):
                continue
            if last_was_main_table and _is_paragraph_note(item):
                expected.context_ranges.extend(text.source for text in _texts(item))
                continue
            last_was_main_table = visit(item)
        return last_was_main_table

    visit(artifact.root)
    return expected


def _range_key(source_range: SourceRange) -> tuple[str, int, int]:
    return (
        source_range.artifact_id,
        source_range.start_byte,
        source_range.end_byte,
    )


def _table_position_span(value: str | None) -> tuple[int, int, int] | None:
    if value is None or (match := _TABLE_POSITION_PATTERN.fullmatch(value)) is None:
        return None
    start = int(match.group("start"))
    return int(match.group("row")), start, int(match.group("end") or start)


_CoverageIndex = dict[str, tuple[tuple[int, int], ...]]


def _coverage_index(ranges: list[SourceRange]) -> _CoverageIndex:
    grouped: dict[str, list[tuple[int, int]]] = {}
    for source_range in ranges:
        grouped.setdefault(source_range.artifact_id, []).append(
            (source_range.start_byte, source_range.end_byte)
        )

    result: _CoverageIndex = {}
    for artifact_id, intervals in grouped.items():
        merged: list[tuple[int, int]] = []
        for start, end in sorted(intervals):
            if not merged or start > merged[-1][1]:
                merged.append((start, end))
            else:
                previous_start, previous_end = merged[-1]
                merged[-1] = (previous_start, max(previous_end, end))
        result[artifact_id] = tuple(merged)
    return result


def _covered(expected: SourceRange, index: _CoverageIndex) -> bool:
    intervals = index.get(expected.artifact_id, ())
    lower = 0
    upper = len(intervals)
    while lower < upper:
        middle = (lower + upper) // 2
        if intervals[middle][0] <= expected.start_byte:
            lower = middle + 1
        else:
            upper = middle
    return lower > 0 and intervals[lower - 1][1] >= expected.end_byte


def _expected_grain_id(grain: DocumentGrain) -> str:
    parts = [grain.doc_id, grain.source.artifact_id, grain.kind]
    for source_range in grain.source.core_ranges:
        parts.extend((str(source_range.start_byte), str(source_range.end_byte)))
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def _validate_core_ranges_do_not_overlap(
    grains: tuple[DocumentGrain, ...], failures: list[str]
) -> None:
    ranges = sorted(
        (
            source_range.artifact_id,
            source_range.start_byte,
            source_range.end_byte,
            grain.grain_id,
        )
        for grain in grains
        for source_range in grain.source.core_ranges
    )
    for left, right in zip(ranges, ranges[1:], strict=False):
        if left[0] == right[0] and right[1] < left[2]:
            failures.append(
                f"overlapping core ranges: {left[3]}[{left[1]}:{left[2]}] and "
                f"{right[3]}[{right[1]}:{right[2]}]"
            )


def _validate_table_cells(
    expected_cells: list[_ExpectedCell],
    grains: tuple[DocumentGrain, ...],
    failures: list[str],
) -> None:
    table_grains = tuple(grain for grain in grains if grain.kind == GrainKind.TABLE)
    core_rows: dict[tuple[str, int, int], list[DocumentGrain]] = {}
    context_rows: dict[tuple[str, int, int], list[DocumentGrain]] = {}
    positioned: dict[tuple[str, int], list[tuple[int, int, DocumentGrain]]] = {}
    for grain in table_grains:
        for source_range in grain.source.core_ranges:
            core_rows.setdefault(_range_key(source_range), []).append(grain)
        for source_range in grain.source.context_ranges:
            context_rows.setdefault(_range_key(source_range), []).append(grain)
        if (position := _table_position_span(grain.context.table_position)) is not None:
            positioned.setdefault((grain.source.artifact_id, position[0]), []).append(
                (position[1], position[2], grain)
            )

    for cell in expected_cells:
        column_pattern = re.compile(rf"\bc{cell.column_ordinal}(?:\[|=)")
        empty_pattern = re.compile(
            rf"\bc{cell.column_ordinal}(?:\[[^]]+\])?=∅"
            rf"(?:[ \t]*\||[ \t]*(?:\n|$))"
        )
        if cell.header:
            candidates = context_rows.get(_range_key(cell.cell_range), [])
            if not candidates:
                failures.append(f"table header row missing from context: {cell.row_range.xpath}")
                continue
            header_lines = tuple(
                line
                for grain in candidates
                for line in grain.context.table_headers
                if line.startswith(f"r{cell.row_ordinal}:")
            )
            if not any(column_pattern.search(line) for line in header_lines):
                failures.append(
                    f"table header cell position marker missing: {cell.cell_range.xpath}"
                )
            if cell.empty and not any(empty_pattern.search(line) for line in header_lines):
                failures.append(f"empty table header cell marker missing: {cell.cell_range.xpath}")
            continue

        row_candidates = core_rows.get(_range_key(cell.row_range), [])
        row_marker = f"r{cell.row_ordinal}:"
        if row_candidates:
            if not any(
                row_marker in grain.core_text and column_pattern.search(grain.core_text)
                for grain in row_candidates
            ):
                failures.append(f"table cell position marker missing: {cell.cell_range.xpath}")
            if cell.empty and not any(
                empty_pattern.search(grain.core_text) for grain in row_candidates
            ):
                failures.append(f"empty table cell marker missing: {cell.cell_range.xpath}")
            continue

        cell_candidates = [
            grain
            for start, end, grain in positioned.get((cell.artifact_id, cell.row_ordinal), [])
            if start <= cell.column_ordinal <= end
            and any(
                source_range.start_byte >= cell.cell_range.start_byte
                and source_range.end_byte <= cell.cell_range.end_byte
                for source_range in grain.source.core_ranges
            )
        ]
        if not cell_candidates:
            failures.append(f"split table cell position missing: {cell.cell_range.xpath}")
        elif not any(column_pattern.search(grain.core_text) for grain in cell_candidates):
            failures.append(f"split table cell marker missing: {cell.cell_range.xpath}")
        elif cell.empty and not any(
            empty_pattern.search(grain.core_text) for grain in cell_candidates
        ):
            failures.append(f"split empty table cell marker missing: {cell.cell_range.xpath}")


def validate_document_grain_set(
    tree: DocumentTree,
    grains: tuple[DocumentGrain, ...],
    *,
    corpus_root: Path,
    max_estimated_tokens: int,
) -> tuple[str, ...]:
    failures: list[str] = []
    if not grains:
        return ("document compiled to zero grains",)

    if [grain.source.ordinal for grain in grains] != list(range(len(grains))):
        failures.append("grain ordinals are not contiguous from zero")
    grain_ids = [grain.grain_id for grain in grains]
    if len(grain_ids) != len(set(grain_ids)):
        failures.append("duplicate grain_id values")
    for index, grain in enumerate(grains):
        if grain.doc_id != tree.doc_id:
            failures.append(f"grain doc_id mismatch: {grain.grain_id}")
        if grain.grain_id != _expected_grain_id(grain):
            failures.append(f"grain_id is not deterministic from source: {grain.grain_id}")
        expected_previous = grain_ids[index - 1] if index > 0 else None
        expected_next = grain_ids[index + 1] if index + 1 < len(grain_ids) else None
        if grain.previous_grain_id != expected_previous:
            failures.append(f"previous link mismatch: {grain.grain_id}")
        if grain.next_grain_id != expected_next:
            failures.append(f"next link mismatch: {grain.grain_id}")
        if estimate_tokens(grain.rendered_text) != grain.estimated_tokens:
            failures.append(f"estimated token count mismatch: {grain.grain_id}")
        if grain.estimated_tokens > max_estimated_tokens:
            failures.append(f"grain exceeds token budget: {grain.grain_id}")
        if DocumentGrain.model_validate_json(grain.model_dump_json()) != grain:
            failures.append(f"grain JSON round-trip changed data: {grain.grain_id}")

    artifact_ids = {artifact.artifact_id for artifact in tree.artifacts}
    grain_artifact_ids = {grain.source.artifact_id for grain in grains}
    if artifact_ids != grain_artifact_ids:
        failures.append(
            f"artifact grain coverage mismatch: expected={sorted(artifact_ids)} "
            f"actual={sorted(grain_artifact_ids)}"
        )

    core_ranges = [source_range for grain in grains for source_range in grain.source.core_ranges]
    context_ranges = [
        source_range for grain in grains for source_range in grain.source.context_ranges
    ]
    _validate_core_ranges_do_not_overlap(grains, failures)

    expectations: list[_Expectations] = []
    for artifact in tree.artifacts:
        source_bytes = (corpus_root / artifact.source_path).read_bytes()
        for grain in grains:
            if grain.source.artifact_id != artifact.artifact_id:
                continue
            for source_range in (*grain.source.core_ranges, *grain.source.context_ranges):
                if source_range.end_byte > len(source_bytes):
                    failures.append(f"grain range exceeds artifact bytes: {source_range.xpath}")
                    continue
                try:
                    source_bytes[source_range.start_byte : source_range.end_byte].decode("utf-8")
                except UnicodeDecodeError:
                    failures.append(f"grain range splits UTF-8 bytes: {source_range.xpath}")
        expectations.append(_artifact_expectations(artifact))

    expected_core = [item for expected in expectations for item in expected.core_ranges]
    expected_context = [item for expected in expectations for item in expected.context_ranges]
    core_coverage = _coverage_index(core_ranges)
    context_coverage = _coverage_index(context_ranges)
    for source_range in expected_core:
        if not _covered(source_range, core_coverage):
            failures.append(f"expected core content is not covered: {source_range.xpath}")
    for source_range in expected_context:
        if not _covered(source_range, context_coverage) and not _covered(
            source_range, core_coverage
        ):
            failures.append(
                f"expected heading is not covered by context or core: {source_range.xpath}"
            )

    _validate_table_cells(
        [cell for expected in expectations for cell in expected.cells],
        grains,
        failures,
    )
    return tuple(dict.fromkeys(failures))


def _validate_document(task: GrainValidationTask) -> DocumentGrainValidationResult:
    for attempt in range(INTERRUPTED_RETRIES + 1):
        try:
            files = tuple(
                path
                for path in task.directory.iterdir()
                if path.is_file() and not path.name.startswith(".")
            )
            if len(files) != task.file_count:
                raise ValueError(
                    f"file count mismatch: manifest={task.file_count} actual={len(files)}"
                )
            tree = compile_document_tree(
                task.directory,
                doc_id=task.doc_id,
                corpus_root=task.corpus_root,
            )
            grains = compile_document_grains(
                tree,
                max_estimated_tokens=task.max_estimated_tokens,
            )
            messages = validate_document_grain_set(
                tree,
                grains,
                corpus_root=task.corpus_root,
                max_estimated_tokens=task.max_estimated_tokens,
            )
            failures = tuple(
                GrainValidationFailure(
                    doc_id=task.doc_id,
                    file_path=task.file_path,
                    error_type="GrainInvariantError",
                    message=message,
                )
                for message in messages
            )
            token_histogram = [0] * (task.max_estimated_tokens + 1)
            kind_counts: dict[str, int] = {}
            for grain in grains:
                token_histogram[grain.estimated_tokens] += 1
                kind_counts[grain.kind.value] = kind_counts.get(grain.kind.value, 0) + 1
            return DocumentGrainValidationResult(
                position=task.position,
                grains=len(grains),
                core_ranges=sum(len(grain.source.core_ranges) for grain in grains),
                context_ranges=sum(len(grain.source.context_ranges) for grain in grains),
                max_estimated_tokens=max(grain.estimated_tokens for grain in grains),
                estimated_token_histogram=tuple(token_histogram),
                grain_kind_counts=tuple(sorted(kind_counts.items())),
                failures=failures,
            )
        except InterruptedError:
            if attempt == INTERRUPTED_RETRIES:
                break
            time.sleep(0.05 * (2**attempt))
        except Exception as error:
            return DocumentGrainValidationResult(
                position=task.position,
                failures=(
                    GrainValidationFailure(
                        doc_id=task.doc_id,
                        file_path=task.file_path,
                        error_type=type(error).__name__,
                        message=str(error),
                    ),
                ),
            )
    return DocumentGrainValidationResult(
        position=task.position,
        failures=(
            GrainValidationFailure(
                doc_id=task.doc_id,
                file_path=task.file_path,
                error_type="InterruptedError",
                message=f"filesystem call remained interrupted after {INTERRUPTED_RETRIES} retries",
            ),
        ),
    )


def _default_workers() -> int:
    configured = os.environ.get("GRAIN_VALIDATION_WORKERS")
    if configured is not None:
        return int(configured)
    return max(1, (os.cpu_count() or 2) - 1)


def _histogram_percentile(histogram: list[int], percentile: float) -> int:
    total = sum(histogram)
    if total == 0:
        return 0
    target = math.ceil(total * percentile)
    cumulative = 0
    for token_count, frequency in enumerate(histogram):
        cumulative += frequency
        if cumulative >= target:
            return token_count
    return len(histogram) - 1


def _histogram_range(histogram: list[int], start: int, end: int | None) -> int:
    return sum(histogram[start:] if end is None else histogram[start : end + 1])


def validate_corpus_grains(
    corpus_root: Path,
    *,
    workers: int = 1,
    progress_every: int = 10,
    fail_fast: bool = False,
    max_estimated_tokens: int = DEFAULT_MAX_ESTIMATED_TOKENS,
) -> CorpusGrainValidationReport:
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if max_estimated_tokens < 1:
        raise ValueError("max_estimated_tokens must be at least 1")

    started_at = time.monotonic()
    corpus_root = corpus_root.resolve()
    documents = read_documents(corpus_root)
    directories = index_document_directories(corpus_root)
    failures: list[GrainValidationFailure] = []

    manifest_paths = [nfc(str(document["file_path"])) for document in documents]
    manifest_path_set = set(manifest_paths)
    filesystem_path_set = set(directories)
    for error_type, paths in (
        ("MissingDocumentDirectory", sorted(manifest_path_set - filesystem_path_set)),
        ("UnlistedDocumentDirectory", sorted(filesystem_path_set - manifest_path_set)),
    ):
        if paths:
            failures.append(
                GrainValidationFailure(
                    doc_id=None,
                    file_path=None,
                    error_type=error_type,
                    message=str(paths),
                )
            )

    tasks = tuple(
        GrainValidationTask(
            position=position,
            doc_id=str(document["doc_id"]),
            file_path=str(document["file_path"]),
            file_count=int(document["file_count"]),
            directory=directory,
            corpus_root=corpus_root,
            max_estimated_tokens=max_estimated_tokens,
        )
        for position, document in enumerate(documents, start=1)
        if (directory := directories.get(nfc(str(document["file_path"])))) is not None
    )

    checked_documents = 0
    compiled_grains = 0
    core_ranges = 0
    context_ranges = 0
    max_tokens_observed = 0
    token_histogram = [0] * (max_estimated_tokens + 1)
    grain_kind_counts = {kind.value: 0 for kind in GrainKind}

    if progress_every > 0:
        print(
            f"starting grain validation: documents={len(tasks)} workers={workers}",
            file=sys.stderr,
            flush=True,
        )

    def collect(result: DocumentGrainValidationResult) -> bool:
        nonlocal checked_documents
        nonlocal compiled_grains
        nonlocal core_ranges
        nonlocal context_ranges
        nonlocal max_tokens_observed
        checked_documents += 1
        compiled_grains += result.grains
        core_ranges += result.core_ranges
        context_ranges += result.context_ranges
        max_tokens_observed = max(max_tokens_observed, result.max_estimated_tokens)
        for token_count, frequency in enumerate(result.estimated_token_histogram):
            token_histogram[token_count] += frequency
        for kind, count in result.grain_kind_counts:
            grain_kind_counts[kind] += count
        failures.extend(result.failures)
        if result.failures:
            first = result.failures[0]
            print(
                f"failed doc_id={first.doc_id} failures={len(result.failures)}; "
                f"first={first.error_type}: {first.message}",
                file=sys.stderr,
                flush=True,
            )
        if progress_every > 0 and checked_documents % progress_every == 0:
            print(
                f"checked {checked_documents}/{len(documents)} documents; "
                f"grains={compiled_grains}; failures={len(failures)}",
                file=sys.stderr,
                flush=True,
            )
        return not (fail_fast and result.failures)

    if workers == 1:
        for task in tasks:
            if not collect(_validate_document(task)):
                break
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            task_iterator = iter(tasks)
            pending: set[Future[DocumentGrainValidationResult]] = {
                executor.submit(_validate_document, task)
                for task in islice(task_iterator, workers * 2)
            }
            stop = False
            while pending and not stop:
                completed, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in completed:
                    if not collect(future.result()):
                        stop = True
                        break
                    try:
                        task = next(task_iterator)
                    except StopIteration:
                        continue
                    pending.add(executor.submit(_validate_document, task))
            if stop:
                for future in pending:
                    future.cancel()

    total_estimated_tokens = sum(
        token_count * frequency for token_count, frequency in enumerate(token_histogram)
    )
    tiny_grains = _histogram_range(token_histogram, 1, 63)
    return CorpusGrainValidationReport(
        passed=not failures,
        manifest_documents=len(documents),
        filesystem_documents=len(directories),
        checked_documents=checked_documents,
        compiled_grains=compiled_grains,
        validated_core_ranges=core_ranges,
        validated_context_ranges=context_ranges,
        max_estimated_tokens=max_tokens_observed,
        average_estimated_tokens=round(
            total_estimated_tokens / compiled_grains if compiled_grains else 0.0,
            3,
        ),
        estimated_token_p50=_histogram_percentile(token_histogram, 0.50),
        estimated_token_p90=_histogram_percentile(token_histogram, 0.90),
        estimated_token_p99=_histogram_percentile(token_histogram, 0.99),
        tiny_grains_under_64=tiny_grains,
        tiny_grain_ratio=round(
            tiny_grains / compiled_grains if compiled_grains else 0.0,
            6,
        ),
        token_bucket_counts={
            "1-31": _histogram_range(token_histogram, 1, 31),
            "32-63": _histogram_range(token_histogram, 32, 63),
            "64-127": _histogram_range(token_histogram, 64, 127),
            "128-255": _histogram_range(token_histogram, 128, 255),
            "256-511": _histogram_range(token_histogram, 256, 511),
            "512-1023": _histogram_range(token_histogram, 512, 1023),
            "1024+": _histogram_range(token_histogram, 1024, None),
        },
        grain_kind_counts=grain_kind_counts,
        elapsed_seconds=round(time.monotonic() - started_at, 3),
        failures=tuple(failures),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile and validate semantic grains for the whole corpus without DB writes."
    )
    parser.add_argument("--corpus-root", type=Path, default=PROJECT_ROOT / "corpus")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument(
        "--workers",
        type=int,
        default=_default_workers(),
        help="Document processes to run in parallel (default: CPU count minus one).",
    )
    parser.add_argument(
        "--max-estimated-tokens",
        type=int,
        default=DEFAULT_MAX_ESTIMATED_TOKENS,
    )
    arguments = parser.parse_args()

    report = validate_corpus_grains(
        arguments.corpus_root,
        workers=arguments.workers,
        progress_every=arguments.progress_every,
        fail_fast=arguments.fail_fast,
        max_estimated_tokens=arguments.max_estimated_tokens,
    )
    report_json = report.model_dump_json(indent=2)
    if arguments.report is not None:
        arguments.report.write_text(f"{report_json}\n", encoding="utf-8")
    print(report_json)
    raise SystemExit(0 if report.passed else 1)


if __name__ == "__main__":
    main()

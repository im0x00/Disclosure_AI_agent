"""Resolve a reproducible subset of documents for development indexing."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class RelationClosure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revises: Literal["both_transitive"]
    references: Literal["outgoing_one_hop"]
    terminates: Literal["outgoing_one_hop"]


class DocumentSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy: Literal["suite_required_documents"]
    suite_path: str = Field(min_length=1)


class SuiteCaseSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    case_ids: tuple[str, ...] = Field(min_length=1)


class MiniWorldSuiteBoundary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    schema_version: Literal["1.0"]
    world_id: str
    case_sources: tuple[SuiteCaseSource, ...] = Field(min_length=1)
    case_count: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_cases(self) -> MiniWorldSuiteBoundary:
        case_ids = [case_id for source in self.case_sources for case_id in source.case_ids]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("mini world suite case_ids must be unique")
        if len(case_ids) != self.case_count:
            raise ValueError("mini world suite case_count does not match case_sources")
        return self


class MiniWorldProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    world_id: str = Field(pattern=r"^[a-z][a-z0-9-]+$")
    company_codes: tuple[str, ...] = Field(min_length=1)
    receipt_date_from: date
    receipt_date_to: date
    document_selection: DocumentSelection
    relation_closure: RelationClosure

    @model_validator(mode="after")
    def validate_profile(self) -> MiniWorldProfile:
        if len(self.company_codes) != len(set(self.company_codes)):
            raise ValueError("company_codes must be unique")
        if any(len(code) != 8 or not code.isdigit() for code in self.company_codes):
            raise ValueError("company_codes must contain eight digits")
        if self.receipt_date_to < self.receipt_date_from:
            raise ValueError("receipt_date_to must not precede receipt_date_from")
        return self


class MiniWorldResolution(BaseModel):
    model_config = ConfigDict(frozen=True)

    world_id: str
    base_document_count: int
    closure_document_count: int
    document_ids: tuple[str, ...]


_OBJECT_ADAPTER = TypeAdapter(dict[str, Any])


def load_mini_world(path: Path) -> MiniWorldProfile:
    return MiniWorldProfile.model_validate_json(path.read_text(encoding="utf-8"))


def resolve_mini_world(
    profile: MiniWorldProfile,
    *,
    profile_path: Path,
    manifest_path: Path,
    relations_path: Path,
) -> MiniWorldResolution:
    documents = _read_jsonl_by_id(manifest_path, id_field="doc_id")
    known_company_codes = {str(row.get("corp_code", "")) for row in documents.values()}
    missing_company_codes = sorted(set(profile.company_codes) - known_company_codes)
    if missing_company_codes:
        raise ValueError(f"mini world contains unknown company codes: {missing_company_codes}")

    selected = _suite_required_document_ids(profile, profile_path=profile_path)
    base_document_count = len(selected)
    if not selected:
        raise ValueError("mini world does not select any manifest documents")
    missing_documents = sorted(selected - documents.keys())
    if missing_documents:
        raise ValueError(f"mini world suite contains unknown documents: {missing_documents}")
    outside_companies = sorted(
        doc_id
        for doc_id in selected
        if str(documents[doc_id].get("corp_code", "")) not in profile.company_codes
    )
    if outside_companies:
        raise ValueError(
            f"mini world suite documents fall outside company_codes: {outside_companies}"
        )

    relations = _read_jsonl(relations_path)
    revision_neighbors: dict[str, set[str]] = defaultdict(set)
    directed_edges: list[tuple[str, str, str]] = []
    for relation in relations:
        source = _required_text(relation, "source_doc_id")
        target = _required_text(relation, "target_doc_id")
        predicate = _required_text(relation, "predicate")
        if source not in documents or target not in documents:
            raise ValueError(f"relation endpoint is absent from manifest: {source} -> {target}")
        if predicate == "revises":
            revision_neighbors[source].add(target)
            revision_neighbors[target].add(source)
        elif predicate in {"references", "terminates"}:
            directed_edges.append((source, predicate, target))

    _expand_transitively(selected, revision_neighbors)
    directed_sources = set(selected)
    for source, _predicate, target in directed_edges:
        if source in directed_sources:
            selected.add(target)
    _expand_transitively(selected, revision_neighbors)

    return MiniWorldResolution(
        world_id=profile.world_id,
        base_document_count=base_document_count,
        closure_document_count=len(selected) - base_document_count,
        document_ids=tuple(sorted(selected)),
    )


def _suite_required_document_ids(
    profile: MiniWorldProfile,
    *,
    profile_path: Path,
) -> set[str]:
    profile_root = profile_path.resolve().parent
    suite_path = _relative_path(profile_root, profile.document_selection.suite_path)
    suite = MiniWorldSuiteBoundary.model_validate_json(suite_path.read_text(encoding="utf-8"))
    if suite.world_id != profile.world_id:
        raise ValueError(
            f"mini world suite world_id mismatch: {suite.world_id} != {profile.world_id}"
        )

    selected: set[str] = set()
    suite_root = suite_path.parent
    for source in suite.case_sources:
        cases_path = _relative_path(suite_root, source.path)
        cases = _read_jsonl_by_id(cases_path, id_field="case_id")
        missing_case_ids = sorted(set(source.case_ids) - cases.keys())
        if missing_case_ids:
            raise ValueError(
                f"mini world suite references missing cases in {cases_path}: {missing_case_ids}"
            )
        for case_id in source.case_ids:
            selected.update(_required_texts(cases[case_id], "required_document_ids"))
    return selected


def _relative_path(root: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError(f"mini world paths must be relative: {value}")
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"mini world path escapes its root: {value}")
    return resolved


def _expand_transitively(selected: set[str], neighbors: dict[str, set[str]]) -> None:
    queue = deque(selected)
    while queue:
        source = queue.popleft()
        for target in neighbors.get(source, ()):
            if target in selected:
                continue
            selected.add(target)
            queue.append(target)


def _read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                rows.append(_OBJECT_ADAPTER.validate_python(json.loads(line)))
            except Exception as error:
                raise ValueError(f"invalid JSON object at {path}:{line_number}") from error
    return tuple(rows)


def _read_jsonl_by_id(path: Path, *, id_field: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(path):
        item_id = _required_text(row, id_field)
        if item_id in result:
            raise ValueError(f"duplicate {id_field} in {path}: {item_id}")
        result[item_id] = row
    return result


def _required_text(row: dict[str, Any], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing string field {field!r}")
    return value


def _required_texts(row: dict[str, Any], field: str) -> tuple[str, ...]:
    value = row.get(field)
    if not isinstance(value, list) or not value:
        raise ValueError(f"missing non-empty string list field {field!r}")
    if any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"field {field!r} must contain only non-empty strings")
    return tuple(value)

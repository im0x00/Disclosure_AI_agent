from __future__ import annotations

import re
from datetime import date
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from evidence.document_relation import RelationPredicate
from reasoning.query_understanding.models import ContextOrigin, ContextStatus

from .models import (
    RelationDirection,
    RelationTraversal,
    RetrievalFrame,
    SearchBatchResult,
    SearchFilters,
    SearchRequest,
    VersionPolicy,
)

_TERM_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
_HISTORY_TERMS = ("정정", "변경 이력", "history", "revision", "revised")
_REFERENCE_TERMS = ("관련공시", "참조", "reference", "referenced", "related disclosure")
_TERMINATION_TERMS = ("해지", "종료 공시", "termination", "terminated")


class VectorMetric(StrEnum):
    COSINE = "cosine"
    INNER_PRODUCT = "inner_product"
    L2 = "l2"


class RetrievalQueryConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    lexical_candidate_k: int = Field(ge=1)
    vector_candidate_k: int = Field(ge=1)
    max_top_k: int = Field(ge=1)
    minimum_score: float
    exhaustive_grain_limit: int = Field(ge=1)
    rrf_k: int = Field(default=60, ge=1)
    vector_metric: VectorMetric = VectorMetric.COSINE


class EmbeddingProvider(Protocol):
    """Embedding boundary; query/document methods allow asymmetric models."""

    async def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...
    @property
    def model_id(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    async def embed_queries(
        self,
        texts: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...]: ...


class CrossEncoder(Protocol):
    async def score(
        self,
        pairs: tuple[tuple[str, str], ...],
    ) -> tuple[float, ...]: ...


class RetrievalSearchBackend(Protocol):
    async def search_many(
        self,
        requests: tuple[SearchRequest, ...],
    ) -> tuple[SearchBatchResult, ...]: ...


class RetrievalQueryCompiler:
    def __init__(self, config: RetrievalQueryConfig) -> None:
        self.config = config

    def compile(
        self,
        frame: RetrievalFrame,
        *,
        today: date | None = None,
    ) -> tuple[SearchRequest, ...]:
        current_date = today or date.today()
        context = _context_values(frame)
        filters = _filters(context)
        as_of = _context_date(context, "as_of") or current_date
        explicit_policy = _first(context, "version_policy")
        exact_doc_ids = filters.exact_doc_ids

        requests: list[SearchRequest] = []
        for index, target in enumerate(frame.evidence_targets):
            query_text = target.need.strip()
            lexical_terms = _lexical_terms(query_text)
            version_policy = _version_policy(
                query_text,
                explicit=explicit_policy,
                has_exact_documents=bool(exact_doc_ids),
            )
            requests.append(
                SearchRequest(
                    target_id=f"target:{index}",
                    target=target,
                    semantic_query=query_text,
                    lexical_terms=lexical_terms,
                    filters=filters,
                    version_policy=version_policy,
                    as_of=as_of,
                    traversals=_relation_traversals(query_text, context),
                    lexical_candidate_k=self.config.lexical_candidate_k,
                    vector_candidate_k=self.config.vector_candidate_k,
                    max_top_k=self.config.max_top_k,
                    minimum_score=self.config.minimum_score,
                )
            )
        return tuple(requests)


def _context_values(frame: RetrievalFrame) -> dict[str, tuple[str, ...]]:
    values: dict[str, list[str]] = {}
    for point in frame.query_understanding.contextual_points:
        if (
            point.value is None
            or point.status != ContextStatus.KNOWN
            or point.origin != ContextOrigin.EXPLICIT
        ):
            continue
        key = point.key.strip().lower()
        values.setdefault(key, []).append(point.value.strip())
    return {key: tuple(items) for key, items in values.items()}


def _filters(context: dict[str, tuple[str, ...]]) -> SearchFilters:
    doc_groups = tuple(
        value.lower()
        for value in context.get("doc_group", ())
        if value.lower() in {"periodic", "major", "exchange", "holding"}
    )
    base_year = _optional_int(_first(context, "base_year"))
    base_month = _optional_int(_first(context, "base_month"))
    return SearchFilters.model_validate(
        {
            "corp_codes": context.get("corp_code", ()),
            "company_names": context.get("company", ()) + context.get("company_name", ()),
            "doc_groups": doc_groups,
            "date_from": _context_date(context, "date_from"),
            "date_to": _context_date(context, "date_to"),
            "base_year": base_year,
            "base_month": base_month,
            "exact_doc_ids": context.get("doc_id", ()),
        }
    )


def _version_policy(
    query_text: str,
    *,
    explicit: str | None,
    has_exact_documents: bool,
) -> VersionPolicy:
    if explicit is not None:
        return VersionPolicy(explicit.lower())
    if has_exact_documents:
        return VersionPolicy.EXACT
    lowered = query_text.lower()
    if any(term in lowered for term in _HISTORY_TERMS):
        return VersionPolicy.ALL_VERSIONS
    return VersionPolicy.LATEST_AS_OF


def _relation_traversals(
    query_text: str,
    context: dict[str, tuple[str, ...]],
) -> tuple[RelationTraversal, ...]:
    lowered = query_text.lower()
    explicit_predicates = tuple(
        RelationPredicate(value.lower()) for value in context.get("relation_predicate", ())
    )
    predicates = list(explicit_predicates)
    if any(term in lowered for term in _HISTORY_TERMS):
        predicates.append(RelationPredicate.REVISES)
    if any(term in lowered for term in _REFERENCE_TERMS):
        predicates.append(RelationPredicate.REFERENCES)
    if any(term in lowered for term in _TERMINATION_TERMS):
        predicates.append(RelationPredicate.TERMINATES)

    explicit_direction = _first(context, "relation_direction")
    traversals: list[RelationTraversal] = []
    for predicate in dict.fromkeys(predicates):
        if predicate == RelationPredicate.REVISES:
            direction = RelationDirection.BOTH
            max_hops = None
        else:
            direction = (
                RelationDirection(explicit_direction.lower())
                if explicit_direction is not None
                else RelationDirection.OUTGOING
            )
            max_hops = 1
        traversals.append(
            RelationTraversal(
                predicate=predicate,
                direction=direction,
                max_hops=max_hops,
            )
        )
    return tuple(traversals)


def _lexical_terms(text: str) -> tuple[str, ...]:
    terms = tuple(
        dict.fromkeys(
            token.lower()
            for token in _TERM_PATTERN.findall(text)
            if len(token) > 1 or token.isdigit()
        )
    )
    if not terms:
        raise ValueError("semantic query must contain at least one searchable term")
    return terms


def _first(context: dict[str, tuple[str, ...]], key: str) -> str | None:
    values = context.get(key, ())
    return values[0] if values else None


def _context_date(context: dict[str, tuple[str, ...]], key: str) -> date | None:
    value = _first(context, key)
    return date.fromisoformat(value) if value is not None else None


def _optional_int(value: str | None) -> int | None:
    return int(value) if value is not None else None

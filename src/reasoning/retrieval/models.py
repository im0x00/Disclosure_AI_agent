from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evidence.document_grain import DocumentGrain
from evidence.document_relation import RelationPredicate
from reasoning.query_understanding.models import ContextPoint, QueryUnderstanding


class EvidenceTarget(BaseModel):
    need: str = Field(min_length=1)
    supported_by: ContextPoint
    operand_id: str | None = None


class RetrievalFrame(BaseModel):
    query_understanding: QueryUnderstanding
    evidence_targets: list[EvidenceTarget] = Field(default_factory=list)


class VersionPolicy(StrEnum):
    LATEST_AS_OF = "latest_as_of"
    EXACT = "exact"
    ALL_VERSIONS = "all_versions"


class RelationDirection(StrEnum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"
    BOTH = "both"


class SearchFilters(BaseModel):
    model_config = ConfigDict(frozen=True)

    corp_codes: tuple[str, ...] = ()
    company_names: tuple[str, ...] = ()
    doc_groups: tuple[Literal["periodic", "major", "exchange", "holding"], ...] = ()
    date_from: date | None = None
    date_to: date | None = None
    base_year: int | None = None
    base_month: int | None = Field(default=None, ge=1, le=12)
    exact_doc_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.date_from is not None and self.date_to is not None:
            if self.date_from > self.date_to:
                raise ValueError("date_from must not be after date_to")
        return self


class RelationTraversal(BaseModel):
    model_config = ConfigDict(frozen=True)

    predicate: RelationPredicate
    direction: RelationDirection
    max_hops: int | None = Field(default=1, ge=1)


class SearchRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_id: str = Field(min_length=1)
    target: EvidenceTarget
    semantic_query: str = Field(min_length=1)
    lexical_terms: tuple[str, ...] = Field(min_length=1)
    filters: SearchFilters
    version_policy: VersionPolicy
    as_of: date
    traversals: tuple[RelationTraversal, ...] = ()
    lexical_candidate_k: int = Field(ge=1)
    vector_candidate_k: int = Field(ge=1)
    max_top_k: int = Field(ge=1)
    minimum_score: float

    @model_validator(mode="after")
    def require_exact_document(self) -> Self:
        if self.version_policy == VersionPolicy.EXACT and not self.filters.exact_doc_ids:
            raise ValueError("exact version policy requires exact_doc_ids")
        return self


class RetrievalScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    lexical: float | None = None
    vector: float | None = None
    rrf: float | None = None
    cross_encoder: float


class RelationDiscoveryMode(StrEnum):
    EXPLICIT = "explicit"
    AUTOMATIC = "automatic"


class RelationHop(BaseModel):
    model_config = ConfigDict(frozen=True)

    discovery_mode: RelationDiscoveryMode = RelationDiscoveryMode.EXPLICIT

    relation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate: RelationPredicate
    source_doc_id: str
    target_doc_id: str
    direction: RelationDirection


class RetrievedGrainRole(StrEnum):
    PRIMARY = "primary"
    RELATED = "related"


class RetrievedGrain(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_id: str
    grain: DocumentGrain
    role: RetrievedGrainRole
    rank: int = Field(ge=1)
    scores: RetrievalScore
    relation_path: tuple[RelationHop, ...] = ()

    @property
    def document_id(self) -> str:
        return self.grain.doc_id

    @property
    def grain_id(self) -> str:
        return self.grain.grain_id

    @property
    def text(self) -> str:
        return self.grain.rendered_text


class SearchBatchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    request: SearchRequest
    hits: tuple[RetrievedGrain, ...] = ()


class RetrievalSearchResult(BaseModel):
    target: EvidenceTarget
    search_results: list[RetrievedGrain] = Field(default_factory=list)


RetrievedEvidence = RetrievedGrain

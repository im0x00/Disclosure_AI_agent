from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReviewStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"


class Answerability(StrEnum):
    ANSWERABLE = "answerable"
    UNANSWERABLE = "unanswerable"


class RawEvidence(BaseModel):
    """A human-reviewable anchor into the immutable raw corpus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    doc_id: str = Field(pattern=r"^[a-z][a-z0-9-]*_[0-9]{14}$")
    source_path: str = Field(pattern=r"^raw/.+")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    start_byte: int = Field(ge=0)
    end_byte: int = Field(gt=0)
    must_contain: tuple[str, ...] = Field(min_length=1)
    note: str
    grain_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_range(self) -> RawEvidence:
        if self.end_byte <= self.start_byte:
            raise ValueError("end_byte must be greater than start_byte")
        return self


class ExpectedFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    value: str
    unit: str | None = None
    period: str | None = None
    scope: str | None = None
    version: str | None = None
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class LogicalQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: str
    entities: tuple[str, ...] = Field(min_length=1)
    metric: str
    period: str | None = None
    scope: str | None = None
    version: str | None = None


class ClaimRubric(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()


class Review(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ReviewStatus = ReviewStatus.DRAFT
    reviewer: str | None = None
    reviewed_at: str | None = None
    note: str = ""

    @model_validator(mode="after")
    def require_approval_metadata(self) -> Review:
        if self.status == ReviewStatus.APPROVED and not (self.reviewer and self.reviewed_at):
            raise ValueError("approved review requires reviewer and reviewed_at")
        return self


class EvalCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    case_id: str = Field(pattern=r"^seed_[0-9]{3}$")
    bucket: Literal["lookup", "calculation", "relation", "unanswerable", "open"]
    question: str
    logical_query: LogicalQuery
    answerability: Answerability
    expected_response: str
    facts: tuple[ExpectedFact, ...] = ()
    required_document_ids: tuple[str, ...] = ()
    evidence: tuple[RawEvidence, ...] = ()
    claims: ClaimRubric = ClaimRubric()
    grading: Literal["exact", "numeric", "checklist"]
    review: Review = Review()

    @model_validator(mode="after")
    def validate_oracle_links(self) -> EvalCase:
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence_id values must be unique within a case")

        known = set(evidence_ids)
        for fact in self.facts:
            missing = set(fact.evidence_ids) - known
            if missing:
                raise ValueError(f"fact references unknown evidence: {sorted(missing)}")

        evidence_docs = {item.doc_id for item in self.evidence}
        missing_docs = set(self.required_document_ids) - evidence_docs
        if missing_docs:
            raise ValueError(f"required documents lack raw evidence: {sorted(missing_docs)}")
        if self.answerability == Answerability.ANSWERABLE and not self.facts:
            raise ValueError("answerable case requires at least one expected fact")
        return self

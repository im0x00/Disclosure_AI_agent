from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from reasoning.computing.models import (
    ComputationResult,
    ComputationValue,
    EvidenceReference,
)
from reasoning.query_understanding.models import ContextPoint
from reasoning.retrieval.models import RetrievalSearchResult


class ClarificationResponse(BaseModel):
    type: Literal["clarification"]
    main_text: str
    missing_context_keys: list[ContextPoint]


class AnswerClaim(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1)
    evidence_refs: tuple[EvidenceReference, ...] = ()
    uses_computation: bool = False
    computed_value: ComputationValue = None

    @model_validator(mode="after")
    def enforce_computation_reference(self) -> Self:
        if not self.uses_computation and self.computed_value is not None:
            raise ValueError("computed_value requires uses_computation=true")
        return self


class FinalResponse(BaseModel):
    type: Literal["final"]
    main_text: str
    claims: tuple[AnswerClaim, ...] = Field(min_length=1)
    evidences: list[RetrievalSearchResult]
    computation: ComputationResult | None = None


class CannotAnswerResponse(BaseModel):
    type: Literal["cannot_answer"]
    main_text: str
    reasons: list[str]


class AnswerVerificationStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class AnswerVerificationIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    claim_index: int | None = Field(default=None, ge=0)


class AnswerVerificationResult(BaseModel):
    status: AnswerVerificationStatus = AnswerVerificationStatus.PASS
    issues: tuple[AnswerVerificationIssue, ...] = ()


Response = Annotated[
    ClarificationResponse | FinalResponse | CannotAnswerResponse,
    Field(discriminator="type"),
]

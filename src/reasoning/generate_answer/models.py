from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from reasoning.computing.models import ComputationResult
from reasoning.query_understanding.models import ContextPoint
from reasoning.retrieval.models import RetrievalSearchResult


class ClarificationResponse(BaseModel):
    type: Literal["clarification"]
    main_text: str
    missing_context_keys: list[ContextPoint]


class FinalResponse(BaseModel):
    type: Literal["final"]
    main_text: str
    evidences: list[RetrievalSearchResult]
    computation: ComputationResult | None = None


class CannotAnswerResponse(BaseModel):
    type: Literal["cannot_answer"]
    main_text: str
    reasons: list[str]


class AnswerVerificationStatus(StrEnum):
    PASS = "pass"


class AnswerVerificationResult(BaseModel):
    status: AnswerVerificationStatus = AnswerVerificationStatus.PASS


Response = Annotated[
    ClarificationResponse | FinalResponse | CannotAnswerResponse,
    Field(discriminator="type"),
]

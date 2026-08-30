from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from reasoning.core.core_models import ComputationIntent


class QuerySafetyResult(BaseModel):
    is_safe: bool
    reason: str


class ContextStatus(StrEnum):
    KNOWN = "known"  # 사용자가 명시함
    INFERRED = "inferred"  # 합리적으로 추론 가능
    AMBIGUOUS = "ambiguous"  # 여러 해석 가능
    MISSING = "missing"  # 필요한데 정보 없음


class ContextOrigin(StrEnum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"


class ContextPoint(BaseModel):
    key: str
    status: ContextStatus
    value: str | None = None  # 알고 있거나 추론한 값
    candidates: list[Any] = Field(default_factory=list)  # ambiguous인 경우 후보
    origin: ContextOrigin = ContextOrigin.EXPLICIT
    raw_span: str | None = None
    critical: bool = False


class QueryUnderstanding(BaseModel):
    question_raw: str
    intention: str
    contextual_points: list[ContextPoint] = Field(default_factory=list)
    needs_clarification: bool
    computation_intent: ComputationIntent | None = None

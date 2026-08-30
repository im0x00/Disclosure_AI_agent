import re
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OperandRequirement(BaseModel):
    model_config = ConfigDict(frozen=True)

    operand_id: str = Field(min_length=1)
    description: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_valid_operand_id(self) -> Self:
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", self.operand_id) is None:
            raise ValueError("operand_id must be an ASCII identifier")
        return self


class ComputationIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    goal: str = Field(min_length=1)
    required_operands: tuple[OperandRequirement, ...] = Field(min_length=1)


class VerificationAction(StrEnum):
    PASS = "pass"
    RETRY_RETRIEVAL = "retry_retrieval"
    RETRY_COMPUTATION = "retry_computation"
    RETRY_UNDERSTANDING = "retry_understanding"
    CANNOT_ANSWER = "cannot_answer"


class VerificationIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    target_id: str | None = None


class CoreVerificationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: VerificationAction
    issues: tuple[VerificationIssue, ...] = ()


class RetryPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_understanding_attempts: int = Field(default=2, ge=1)
    max_retrieval_attempts: int = Field(default=3, ge=1)
    max_computation_attempts: int = Field(default=2, ge=1)


class RuntimeFailure(BaseModel):
    model_config = ConfigDict(frozen=True)

    node: str = Field(min_length=1)
    attempts: int = Field(ge=1)
    error_type: str = Field(min_length=1)

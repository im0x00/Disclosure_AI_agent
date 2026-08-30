from __future__ import annotations

import re
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

type ComputationValue = (
    Decimal | bool | str | None | list[ComputationValue] | dict[str, ComputationValue]
)
type ReferencePathPart = str | int


class DSLVersion(StrEnum):
    V1 = "1"


class Primitive(StrEnum):
    ADD = "add"
    SUBTRACT = "subtract"
    MULTIPLY = "multiply"
    DIVIDE = "divide"
    ABSOLUTE = "absolute"

    SUM = "sum"
    COUNT = "count"
    MIN = "min"
    MAX = "max"

    EQUAL = "equal"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    AND = "and"
    OR = "or"
    NOT = "not"
    IF = "if"

    FILTER = "filter"
    GROUP_BY = "group_by"
    SORT = "sort"
    TAKE = "take"
    DISTINCT = "distinct"


class EvidenceReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str
    grain_id: str = Field(pattern=r"^[0-9a-f]{64}$")


class Operand(BaseModel):
    """A validated value made available to a computation plan."""

    model_config = ConfigDict(frozen=True)

    operand_id: str = Field(min_length=1)
    value: ComputationValue
    unit: str | None = None
    period: str | None = None
    scope: str | None = None
    evidence_refs: tuple[EvidenceReference, ...] = ()

    @model_validator(mode="after")
    def reject_reserved_ids(self) -> Operand:
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", self.operand_id) is None:
            raise ValueError("operand_id must be an ASCII identifier")
        if self.operand_id in {"item", "index"}:
            raise ValueError("operand_id is reserved by the collection expression runtime")
        return self


class OperandBindingResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    operands: tuple[Operand, ...] = ()
    missing_operand_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_unique_operand_ids(self) -> OperandBindingResult:
        operand_ids = [operand.operand_id for operand in self.operands]
        if len(operand_ids) != len(set(operand_ids)):
            raise ValueError("bound operand_id values must be unique")
        return self


class ReferenceExpression(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["reference"] = "reference"
    name: str = Field(min_length=1)
    path: tuple[ReferencePathPart, ...] = ()


class ConstantExpression(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["constant"] = "constant"
    value: Decimal | bool | str = Field(union_mode="left_to_right")


class OperationExpression(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["operation"] = "operation"
    op: Primitive
    arguments: tuple[Expression, ...]


Expression = Annotated[
    ReferenceExpression | ConstantExpression | OperationExpression,
    Field(discriminator="kind"),
]
OperationExpression.model_rebuild()


class ComputationPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: DSLVersion = DSLVersion.V1
    goal: str = Field(min_length=1)
    expression: Expression


class ComputationPlanningResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan: ComputationPlan | None = None
    unsupported_reason: str | None = None

    @model_validator(mode="after")
    def require_plan_or_reason(self) -> ComputationPlanningResult:
        if (self.plan is None) == (self.unsupported_reason is None):
            raise ValueError("exactly one of plan or unsupported_reason is required")
        return self


class ComputationStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class ComputationErrorCode(StrEnum):
    INVALID_PLAN = "invalid_plan"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    MISSING_OPERAND = "missing_operand"
    INVALID_REFERENCE = "invalid_reference"
    TYPE_MISMATCH = "type_mismatch"
    UNIT_MISMATCH = "unit_mismatch"
    DIVISION_BY_ZERO = "division_by_zero"
    LIMIT_EXCEEDED = "limit_exceeded"
    EXECUTION_ERROR = "execution_error"


class ComputationError(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: ComputationErrorCode
    message: str
    expression_path: str = "$"
    retryable: bool


class ExecutionStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    expression_path: str
    primitive: Primitive
    result: ComputationValue


class ComputationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ComputationStatus
    plan: ComputationPlan
    value: ComputationValue = None
    unit: str | None = None
    evidence_refs: tuple[EvidenceReference, ...] = ()
    steps: tuple[ExecutionStep, ...] = ()
    error: ComputationError | None = None

    @model_validator(mode="after")
    def enforce_status_contract(self) -> ComputationResult:
        if self.status == ComputationStatus.SUCCESS and self.error is not None:
            raise ValueError("a successful computation cannot contain an error")
        if self.status == ComputationStatus.FAILURE and self.error is None:
            raise ValueError("a failed computation must contain an error")
        return self

from dataclasses import dataclass

from .models import (
    ComputationErrorCode,
    ComputationPlan,
    DSLVersion,
    Expression,
    Operand,
    OperationExpression,
    Primitive,
    ReferenceExpression,
)

PRIMITIVES_BY_VERSION: dict[DSLVersion, frozenset[Primitive]] = {
    DSLVersion.V1: frozenset(Primitive),
}

_ARITY: dict[Primitive, frozenset[int]] = {
    Primitive.ADD: frozenset({2}),
    Primitive.SUBTRACT: frozenset({2}),
    Primitive.MULTIPLY: frozenset({2}),
    Primitive.DIVIDE: frozenset({2}),
    Primitive.ABSOLUTE: frozenset({1}),
    Primitive.SUM: frozenset({1}),
    Primitive.COUNT: frozenset({1}),
    Primitive.MIN: frozenset({1}),
    Primitive.MAX: frozenset({1}),
    Primitive.EQUAL: frozenset({2}),
    Primitive.GREATER_THAN: frozenset({2}),
    Primitive.LESS_THAN: frozenset({2}),
    Primitive.AND: frozenset({2}),
    Primitive.OR: frozenset({2}),
    Primitive.NOT: frozenset({1}),
    Primitive.IF: frozenset({3}),
    Primitive.FILTER: frozenset({2}),
    Primitive.GROUP_BY: frozenset({2}),
    Primitive.SORT: frozenset({2, 3}),
    Primitive.TAKE: frozenset({2}),
    Primitive.DISTINCT: frozenset({1, 2}),
}

_CALLBACK_ARGUMENT: dict[Primitive, int] = {
    Primitive.FILTER: 1,
    Primitive.GROUP_BY: 1,
    Primitive.SORT: 1,
    Primitive.DISTINCT: 1,
}


@dataclass(frozen=True)
class PlanCompilationError(ValueError):
    code: ComputationErrorCode
    message: str
    expression_path: str
    retryable: bool = True

    def __str__(self) -> str:
        return self.message


class ComputationCompiler:
    def __init__(self, *, max_depth: int = 32, max_nodes: int = 256) -> None:
        self.max_depth = max_depth
        self.max_nodes = max_nodes

    def compile(self, plan: ComputationPlan, operands: tuple[Operand, ...]) -> None:
        operand_names = [operand.operand_id for operand in operands]
        if len(operand_names) != len(set(operand_names)):
            raise PlanCompilationError(
                code=ComputationErrorCode.INVALID_PLAN,
                message="operand_id values must be unique",
                expression_path="$",
            )

        nodes_seen = [0]
        self._walk(
            plan.expression,
            path="$.expression",
            depth=1,
            available_references=frozenset(operand_names),
            allowed_primitives=PRIMITIVES_BY_VERSION[plan.version],
            nodes_seen=nodes_seen,
        )

    def _walk(
        self,
        expression: Expression,
        *,
        path: str,
        depth: int,
        available_references: frozenset[str],
        allowed_primitives: frozenset[Primitive],
        nodes_seen: list[int],
    ) -> None:
        nodes_seen[0] += 1
        if depth > self.max_depth or nodes_seen[0] > self.max_nodes:
            raise PlanCompilationError(
                code=ComputationErrorCode.LIMIT_EXCEEDED,
                message="computation plan exceeds the configured size limit",
                expression_path=path,
            )

        if isinstance(expression, ReferenceExpression):
            if expression.name not in available_references:
                code = (
                    ComputationErrorCode.MISSING_OPERAND
                    if expression.name not in {"item", "index"}
                    else ComputationErrorCode.INVALID_REFERENCE
                )
                raise PlanCompilationError(
                    code=code,
                    message=f"reference is not available here: {expression.name}",
                    expression_path=path,
                )
            return

        if not isinstance(expression, OperationExpression):
            return

        if expression.op not in allowed_primitives:
            raise PlanCompilationError(
                code=ComputationErrorCode.UNSUPPORTED_OPERATION,
                message=f"primitive is not available in this DSL version: {expression.op}",
                expression_path=path,
                retryable=False,
            )

        if len(expression.arguments) not in _ARITY[expression.op]:
            expected = sorted(_ARITY[expression.op])
            raise PlanCompilationError(
                code=ComputationErrorCode.INVALID_PLAN,
                message=f"{expression.op} expects argument counts {expected}",
                expression_path=path,
            )

        callback_index = _CALLBACK_ARGUMENT.get(expression.op)
        for index, argument in enumerate(expression.arguments):
            callback_references = available_references
            if callback_index == index:
                callback_references |= {"item", "index"}
            self._walk(
                argument,
                path=f"{path}.arguments[{index}]",
                depth=depth + 1,
                available_references=callback_references,
                allowed_primitives=allowed_primitives,
                nodes_seen=nodes_seen,
            )

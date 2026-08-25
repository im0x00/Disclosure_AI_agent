from dataclasses import dataclass
from decimal import Decimal

from .compiler import ComputationCompiler, PlanCompilationError
from .models import (
    ComputationError,
    ComputationErrorCode,
    ComputationPlan,
    ComputationResult,
    ComputationStatus,
    ComputationValue,
    ConstantExpression,
    EvidenceReference,
    ExecutionStep,
    Expression,
    Operand,
    OperationExpression,
    Primitive,
    ReferenceExpression,
)
from .primitives import (
    PrimitiveExecutionError,
    absolute,
    add,
    aggregate_sum,
    count,
    distinct,
    divide,
    equal,
    filter_values,
    greater_than,
    group_by,
    less_than,
    logical_and,
    logical_not,
    logical_or,
    maximum,
    minimum,
    multiply,
    require_boolean,
    sort_values,
    subtract,
    take,
)


@dataclass(frozen=True)
class _Evaluated:
    value: ComputationValue
    unit: str | None = None
    evidence_refs: tuple[EvidenceReference, ...] = ()


@dataclass
class _EvaluationContext:
    operands: dict[str, Operand]
    steps: list[ExecutionStep]


class EvaluationError(ValueError):
    def __init__(
        self,
        code: ComputationErrorCode,
        message: str,
        expression_path: str,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.expression_path = expression_path


class ComputationExecutor:
    def __init__(self, compiler: ComputationCompiler | None = None) -> None:
        self.compiler = compiler or ComputationCompiler()

    def execute(
        self,
        plan: ComputationPlan,
        operands: tuple[Operand, ...],
    ) -> ComputationResult:
        try:
            self.compiler.compile(plan, operands)
            context = _EvaluationContext(
                operands={operand.operand_id: operand for operand in operands},
                steps=[],
            )
            evaluated = self._evaluate(
                plan.expression,
                path="$.expression",
                locals_={},
                context=context,
            )
            return ComputationResult(
                status=ComputationStatus.SUCCESS,
                plan=plan,
                value=evaluated.value,
                unit=evaluated.unit,
                evidence_refs=evaluated.evidence_refs,
                steps=tuple(context.steps),
            )
        except PlanCompilationError as error:
            return self._failure(
                plan,
                code=error.code,
                message=error.message,
                path=error.expression_path,
                retryable=error.retryable,
            )
        except EvaluationError as error:
            return self._failure(
                plan,
                code=error.code,
                message=str(error),
                path=error.expression_path,
                retryable=True,
            )

    def _evaluate(
        self,
        expression: Expression,
        *,
        path: str,
        locals_: dict[str, _Evaluated],
        context: _EvaluationContext,
    ) -> _Evaluated:
        if isinstance(expression, ConstantExpression):
            return _Evaluated(value=expression.value)
        if isinstance(expression, ReferenceExpression):
            return self._resolve_reference(
                expression,
                path=path,
                locals_=locals_,
                context=context,
            )

        try:
            return self._evaluate_operation(
                expression,
                path=path,
                locals_=locals_,
                context=context,
            )
        except ZeroDivisionError as error:
            raise EvaluationError(
                ComputationErrorCode.DIVISION_BY_ZERO,
                str(error),
                path,
            ) from error
        except PrimitiveExecutionError as error:
            raise EvaluationError(
                ComputationErrorCode.TYPE_MISMATCH,
                str(error),
                path,
            ) from error

    def _evaluate_operation(
        self,
        expression: OperationExpression,
        *,
        path: str,
        locals_: dict[str, _Evaluated],
        context: _EvaluationContext,
    ) -> _Evaluated:
        if expression.op == Primitive.IF:
            condition = self._evaluate_argument(expression, 0, path, locals_, context)
            branch = 1 if require_boolean(condition.value, "if") else 2
            selected = self._evaluate_argument(expression, branch, path, locals_, context)
            result = _Evaluated(
                value=selected.value,
                unit=selected.unit,
                evidence_refs=self._merge_refs(condition, selected),
            )
        elif expression.op == Primitive.AND:
            left = self._evaluate_argument(expression, 0, path, locals_, context)
            if not require_boolean(left.value, "and"):
                result = _Evaluated(value=False, evidence_refs=left.evidence_refs)
            else:
                right = self._evaluate_argument(expression, 1, path, locals_, context)
                result = _Evaluated(
                    value=require_boolean(right.value, "and"),
                    evidence_refs=self._merge_refs(left, right),
                )
        elif expression.op == Primitive.OR:
            left = self._evaluate_argument(expression, 0, path, locals_, context)
            if require_boolean(left.value, "or"):
                result = _Evaluated(value=True, evidence_refs=left.evidence_refs)
            else:
                right = self._evaluate_argument(expression, 1, path, locals_, context)
                result = _Evaluated(
                    value=require_boolean(right.value, "or"),
                    evidence_refs=self._merge_refs(left, right),
                )
        elif expression.op in {
            Primitive.FILTER,
            Primitive.GROUP_BY,
            Primitive.SORT,
            Primitive.DISTINCT,
        }:
            result = self._evaluate_collection_operation(
                expression,
                path=path,
                locals_=locals_,
                context=context,
            )
        else:
            arguments = [
                self._evaluate_argument(expression, index, path, locals_, context)
                for index in range(len(expression.arguments))
            ]
            result = self._apply_eager(expression.op, arguments, path=path)

        context.steps.append(
            ExecutionStep(expression_path=path, primitive=expression.op, result=result.value)
        )
        return result

    def _evaluate_collection_operation(
        self,
        expression: OperationExpression,
        *,
        path: str,
        locals_: dict[str, _Evaluated],
        context: _EvaluationContext,
    ) -> _Evaluated:
        collection = self._evaluate_argument(expression, 0, path, locals_, context)
        callback_refs: list[EvidenceReference] = []
        extra_refs: tuple[EvidenceReference, ...] = ()

        def callback(item: ComputationValue, index: int) -> ComputationValue:
            callback_locals = dict(locals_)
            callback_locals["item"] = _Evaluated(
                value=item,
                unit=collection.unit,
                evidence_refs=collection.evidence_refs,
            )
            callback_locals["index"] = _Evaluated(value=Decimal(index))
            callback_result = self._evaluate_argument(
                expression,
                1,
                path,
                callback_locals,
                context,
            )
            for reference in callback_result.evidence_refs:
                if reference not in callback_refs:
                    callback_refs.append(reference)
            return callback_result.value

        if expression.op == Primitive.FILTER:
            value = filter_values(collection.value, callback)
        elif expression.op == Primitive.GROUP_BY:
            value = group_by(collection.value, callback)
        elif expression.op == Primitive.SORT:
            descending = False
            if len(expression.arguments) == 3:
                descending_value = self._evaluate_argument(
                    expression,
                    2,
                    path,
                    locals_,
                    context,
                )
                descending = require_boolean(descending_value.value, "sort")
                extra_refs = descending_value.evidence_refs
            value = sort_values(collection.value, callback, descending)
        else:
            if len(expression.arguments) == 1:
                value = distinct(collection.value, lambda item, _: item)
            else:
                value = distinct(collection.value, callback)

        return _Evaluated(
            value=value,
            unit=collection.unit,
            evidence_refs=self._merge_refs(
                collection,
                _Evaluated(value=None, evidence_refs=tuple(callback_refs)),
                _Evaluated(value=None, evidence_refs=extra_refs)
                if expression.op == Primitive.SORT
                else _Evaluated(value=None),
            ),
        )

    def _evaluate_argument(
        self,
        expression: OperationExpression,
        index: int,
        path: str,
        locals_: dict[str, _Evaluated],
        context: _EvaluationContext,
    ) -> _Evaluated:
        return self._evaluate(
            expression.arguments[index],
            path=f"{path}.arguments[{index}]",
            locals_=locals_,
            context=context,
        )

    def _apply_eager(
        self,
        operation: Primitive,
        arguments: list[_Evaluated],
        *,
        path: str,
    ) -> _Evaluated:
        values = [argument.value for argument in arguments]
        refs = self._merge_refs(*arguments)
        unit = self._unit_for(operation, arguments, path=path)
        value: ComputationValue
        match operation:
            case Primitive.ADD:
                value = add(values[0], values[1])
            case Primitive.SUBTRACT:
                value = subtract(values[0], values[1])
            case Primitive.MULTIPLY:
                value = multiply(values[0], values[1])
            case Primitive.DIVIDE:
                value = divide(values[0], values[1])
            case Primitive.ABSOLUTE:
                value = absolute(values[0])
            case Primitive.SUM:
                value = aggregate_sum(values[0])
            case Primitive.COUNT:
                value = count(values[0])
            case Primitive.MIN:
                value = minimum(values[0])
            case Primitive.MAX:
                value = maximum(values[0])
            case Primitive.EQUAL:
                value = equal(values[0], values[1])
            case Primitive.GREATER_THAN:
                value = greater_than(values[0], values[1])
            case Primitive.LESS_THAN:
                value = less_than(values[0], values[1])
            case Primitive.AND:
                value = logical_and(values[0], values[1])
            case Primitive.OR:
                value = logical_or(values[0], values[1])
            case Primitive.NOT:
                value = logical_not(values[0])
            case Primitive.TAKE:
                value = take(values[0], values[1])
            case _:
                raise EvaluationError(
                    ComputationErrorCode.UNSUPPORTED_OPERATION,
                    f"executor does not implement primitive: {operation}",
                    path,
                )
        return _Evaluated(value=value, unit=unit, evidence_refs=refs)

    def _resolve_reference(
        self,
        expression: ReferenceExpression,
        *,
        path: str,
        locals_: dict[str, _Evaluated],
        context: _EvaluationContext,
    ) -> _Evaluated:
        if expression.name in locals_:
            resolved = locals_[expression.name]
        else:
            operand = context.operands[expression.name]
            resolved = _Evaluated(
                value=operand.value,
                unit=operand.unit,
                evidence_refs=operand.evidence_refs,
            )

        value = resolved.value
        for part in expression.path:
            if isinstance(value, dict) and isinstance(part, str) and part in value:
                value = value[part]
            elif (
                isinstance(value, list)
                and isinstance(part, int)
                and -len(value) <= part < len(value)
            ):
                value = value[part]
            else:
                raise EvaluationError(
                    ComputationErrorCode.INVALID_REFERENCE,
                    f"reference path does not exist: {expression.name}{expression.path}",
                    path,
                )
        return _Evaluated(
            value=value,
            unit=resolved.unit,
            evidence_refs=resolved.evidence_refs,
        )

    def _unit_for(
        self,
        operation: Primitive,
        arguments: list[_Evaluated],
        *,
        path: str,
    ) -> str | None:
        units = [argument.unit for argument in arguments]
        if operation in {
            Primitive.ADD,
            Primitive.SUBTRACT,
            Primitive.SUM,
            Primitive.MIN,
            Primitive.MAX,
            Primitive.ABSOLUTE,
        }:
            if len(set(units)) > 1:
                raise EvaluationError(
                    ComputationErrorCode.UNIT_MISMATCH,
                    f"{operation} cannot combine units: {units}",
                    path,
                )
            return units[0] if units else None
        if operation in {Primitive.EQUAL, Primitive.GREATER_THAN, Primitive.LESS_THAN}:
            if len(set(units)) > 1:
                raise EvaluationError(
                    ComputationErrorCode.UNIT_MISMATCH,
                    f"{operation} cannot compare units: {units}",
                    path,
                )
            return None
        if operation == Primitive.MULTIPLY:
            if units[0] is None:
                return units[1]
            if units[1] is None:
                return units[0]
            return f"{units[0]}*{units[1]}"
        if operation == Primitive.DIVIDE:
            if units[0] == units[1]:
                return None
            if units[1] is None:
                return units[0]
            return f"{units[0] or '1'}/{units[1]}"
        if operation in {
            Primitive.COUNT,
            Primitive.EQUAL,
            Primitive.AND,
            Primitive.OR,
            Primitive.NOT,
        }:
            return None
        return units[0] if units else None

    @staticmethod
    def _merge_refs(*values: _Evaluated) -> tuple[EvidenceReference, ...]:
        merged: list[EvidenceReference] = []
        for value in values:
            for reference in value.evidence_refs:
                if reference not in merged:
                    merged.append(reference)
        return tuple(merged)

    @staticmethod
    def _failure(
        plan: ComputationPlan,
        *,
        code: ComputationErrorCode,
        message: str,
        path: str,
        retryable: bool,
    ) -> ComputationResult:
        return ComputationResult(
            status=ComputationStatus.FAILURE,
            plan=plan,
            error=ComputationError(
                code=code,
                message=message,
                expression_path=path,
                retryable=retryable,
            ),
        )

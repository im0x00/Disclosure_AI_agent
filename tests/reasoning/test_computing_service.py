import asyncio
from decimal import Decimal
from typing import cast
from unittest.mock import Mock

from langchain_core.language_models import BaseChatModel

from reasoning.computing import (
    ComputationErrorCode,
    ComputationPlan,
    ComputationPlanningResult,
    ComputationPlanningService,
    ComputationResult,
    ComputationService,
    ComputationStatus,
    ComputationValue,
    ConstantExpression,
    EvidenceReference,
    Expression,
    Operand,
    OperationExpression,
    Primitive,
    ReferenceExpression,
)


def test_planning_service_returns_structured_ast() -> None:
    planned = ComputationPlanningResult(
        plan=ComputationPlan(
            goal="ratio",
            expression=_op(Primitive.DIVIDE, _ref("left"), _ref("right")),
        )
    )
    runnable = _StructuredPlanner(planned)
    llm = Mock(spec=BaseChatModel)
    llm.with_structured_output.return_value = runnable
    service = ComputationPlanningService(cast(BaseChatModel, llm))

    result = asyncio.run(
        service.plan(
            "What is the ratio?",
            (_operand("left", Decimal("10")), _operand("right", Decimal("2"))),
        )
    )

    assert result == planned
    llm.with_structured_output.assert_called_once_with(
        ComputationPlanningResult,
        method="json_schema",
    )


def test_scalar_aggregate_comparison_and_logic_primitives() -> None:
    operands = (
        _operand("left", Decimal("10")),
        _operand("right", Decimal("4")),
        _operand("negative", Decimal("-3")),
        _operand("values", [Decimal("2"), Decimal("8"), Decimal("5")]),
    )
    expressions: list[tuple[Expression, object]] = [
        (_op(Primitive.ADD, _ref("left"), _ref("right")), Decimal("14")),
        (_op(Primitive.SUBTRACT, _ref("left"), _ref("right")), Decimal("6")),
        (_op(Primitive.MULTIPLY, _ref("left"), _ref("right")), Decimal("40")),
        (_op(Primitive.DIVIDE, _ref("left"), _ref("right")), Decimal("2.5")),
        (_op(Primitive.ABSOLUTE, _ref("negative")), Decimal("3")),
        (_op(Primitive.SUM, _ref("values")), Decimal("15")),
        (_op(Primitive.COUNT, _ref("values")), Decimal("3")),
        (_op(Primitive.MIN, _ref("values")), Decimal("2")),
        (_op(Primitive.MAX, _ref("values")), Decimal("8")),
        (_op(Primitive.EQUAL, _ref("left"), _const("10")), True),
        (_op(Primitive.GREATER_THAN, _ref("left"), _ref("right")), True),
        (_op(Primitive.LESS_THAN, _ref("right"), _ref("left")), True),
        (_op(Primitive.AND, _const(True), _const(True)), True),
        (_op(Primitive.OR, _const(False), _const(True)), True),
        (_op(Primitive.NOT, _const(False)), True),
        (_op(Primitive.IF, _const(True), _ref("left"), _ref("right")), Decimal("10")),
    ]

    for expression, expected in expressions:
        result = _compute(expression, operands)
        assert result.status == ComputationStatus.SUCCESS
        assert result.value == expected


def test_collection_primitives_use_item_binding() -> None:
    rows: list[ComputationValue] = [
        {"company": "A", "sector": "battery", "value": Decimal("10")},
        {"company": "B", "sector": "chip", "value": Decimal("30")},
        {"company": "C", "sector": "battery", "value": Decimal("20")},
    ]
    operands = (_operand("rows", rows),)

    filtered = _compute(
        _op(
            Primitive.FILTER,
            _ref("rows"),
            _op(Primitive.GREATER_THAN, _ref("item", "value"), _const("15")),
        ),
        operands,
    )
    grouped = _compute(
        _op(Primitive.GROUP_BY, _ref("rows"), _ref("item", "sector")),
        operands,
    )
    sorted_rows = _compute(
        _op(Primitive.SORT, _ref("rows"), _ref("item", "value"), _const(True)),
        operands,
    )
    top_two = _compute(
        _op(
            Primitive.TAKE,
            _op(Primitive.SORT, _ref("rows"), _ref("item", "value"), _const(True)),
            _const("2"),
        ),
        operands,
    )
    distinct_sectors = _compute(
        _op(Primitive.DISTINCT, _ref("rows"), _ref("item", "sector")),
        operands,
    )

    assert [row["company"] for row in _records(filtered)] == ["B", "C"]
    assert [group["key"] for group in _records(grouped)] == ["battery", "chip"]
    assert [row["company"] for row in _records(sorted_rows)] == ["B", "C", "A"]
    assert [row["company"] for row in _records(top_two)] == ["B", "C"]
    assert [row["sector"] for row in _records(distinct_sectors)] == ["battery", "chip"]


def test_growth_rate_average_ratio_and_ranking_are_compositions() -> None:
    operands = (
        _operand("current", Decimal("120")),
        _operand("previous", Decimal("100")),
        _operand("values", [Decimal("10"), Decimal("30"), Decimal("20")]),
        _operand("target", Decimal("20")),
    )
    growth_rate = _op(
        Primitive.MULTIPLY,
        _op(
            Primitive.DIVIDE,
            _op(Primitive.SUBTRACT, _ref("current"), _ref("previous")),
            _ref("previous"),
        ),
        _const("100"),
    )
    average = _op(
        Primitive.DIVIDE,
        _op(Primitive.SUM, _ref("values")),
        _op(Primitive.COUNT, _ref("values")),
    )
    ratio = _op(Primitive.DIVIDE, _ref("current"), _ref("previous"))
    ranking = _op(
        Primitive.ADD,
        _op(
            Primitive.COUNT,
            _op(
                Primitive.FILTER,
                _ref("values"),
                _op(Primitive.GREATER_THAN, _ref("item"), _ref("target")),
            ),
        ),
        _const("1"),
    )

    assert _compute(growth_rate, operands).value == Decimal("20")
    assert _compute(average, operands).value == Decimal("20")
    assert _compute(ratio, operands).value == Decimal("1.2")
    assert _compute(ranking, operands).value == Decimal("2")


def test_compiler_and_executor_return_typed_failures() -> None:
    missing = _compute(_ref("missing"), ())
    wrong_arity = _compute(_op(Primitive.ADD, _const("1")), ())
    invalid_item = _compute(_ref("item"), ())
    zero_division = _compute(
        _op(Primitive.DIVIDE, _const("1"), _const("0")),
        (),
    )
    unit_mismatch = _compute(
        _op(Primitive.ADD, _ref("krw"), _ref("usd")),
        (
            _operand("krw", Decimal("1"), unit="KRW"),
            _operand("usd", Decimal("1"), unit="USD"),
        ),
    )

    assert missing.error is not None
    assert missing.error.code == ComputationErrorCode.MISSING_OPERAND
    assert wrong_arity.error is not None
    assert wrong_arity.error.code == ComputationErrorCode.INVALID_PLAN
    assert invalid_item.error is not None
    assert invalid_item.error.code == ComputationErrorCode.INVALID_REFERENCE
    assert zero_division.error is not None
    assert zero_division.error.code == ComputationErrorCode.DIVISION_BY_ZERO
    assert unit_mismatch.error is not None
    assert unit_mismatch.error.code == ComputationErrorCode.UNIT_MISMATCH


def test_result_preserves_evidence_trace_and_execution_steps() -> None:
    reference = EvidenceReference(
        document_id="periodic_20250000000001",
        grain_id="1" * 64,
    )
    result = _compute(
        _op(Primitive.ADD, _ref("amount"), _const("5")),
        (_operand("amount", Decimal("10"), evidence_refs=(reference,)),),
    )

    assert result.evidence_refs == (reference,)
    assert result.steps[-1].primitive == Primitive.ADD
    assert result.steps[-1].result == Decimal("15")


def _compute(expression: Expression, operands: tuple[Operand, ...]) -> ComputationResult:
    plan = ComputationPlan(goal="test computation", expression=expression)
    return ComputationService().compute(plan, operands)


def _operand(
    operand_id: str,
    value: ComputationValue,
    *,
    unit: str | None = None,
    evidence_refs: tuple[EvidenceReference, ...] = (),
) -> Operand:
    return Operand.model_validate(
        {
            "operand_id": operand_id,
            "value": value,
            "unit": unit,
            "evidence_refs": evidence_refs,
        }
    )


def _ref(name: str, *path: str | int) -> ReferenceExpression:
    return ReferenceExpression(name=name, path=path)


def _const(value: Decimal | bool | str) -> ConstantExpression:
    return ConstantExpression(value=value)


def _op(primitive: Primitive, *arguments: Expression) -> OperationExpression:
    return OperationExpression(op=primitive, arguments=arguments)


def _records(result: ComputationResult) -> list[dict[str, ComputationValue]]:
    assert isinstance(result.value, list)
    assert all(isinstance(item, dict) for item in result.value)
    return cast(list[dict[str, ComputationValue]], result.value)


class _StructuredPlanner:
    def __init__(self, result: ComputationPlanningResult) -> None:
        self.result = result

    async def ainvoke(self, _: object) -> ComputationPlanningResult:
        return self.result

from collections.abc import Callable
from decimal import Decimal
from typing import TypeGuard, cast

from .models import ComputationValue


class PrimitiveExecutionError(ValueError):
    pass


def is_decimal(value: ComputationValue) -> TypeGuard[Decimal]:
    return isinstance(value, Decimal)


def require_decimal(value: ComputationValue, operation: str) -> Decimal:
    if not is_decimal(value):
        raise PrimitiveExecutionError(f"{operation} requires Decimal operands")
    return value


def require_boolean(value: ComputationValue, operation: str) -> bool:
    if not isinstance(value, bool):
        raise PrimitiveExecutionError(f"{operation} requires boolean operands")
    return value


def require_collection(value: ComputationValue, operation: str) -> list[ComputationValue]:
    if not isinstance(value, list):
        raise PrimitiveExecutionError(f"{operation} requires a collection operand")
    return value


def add(left: ComputationValue, right: ComputationValue) -> Decimal:
    return require_decimal(left, "add") + require_decimal(right, "add")


def subtract(left: ComputationValue, right: ComputationValue) -> Decimal:
    return require_decimal(left, "subtract") - require_decimal(right, "subtract")


def multiply(left: ComputationValue, right: ComputationValue) -> Decimal:
    return require_decimal(left, "multiply") * require_decimal(right, "multiply")


def divide(left: ComputationValue, right: ComputationValue) -> Decimal:
    denominator = require_decimal(right, "divide")
    if denominator == 0:
        raise ZeroDivisionError("divide cannot use a zero denominator")
    return require_decimal(left, "divide") / denominator


def absolute(value: ComputationValue) -> Decimal:
    return abs(require_decimal(value, "absolute"))


def aggregate_sum(value: ComputationValue) -> Decimal:
    values = require_collection(value, "sum")
    return sum((require_decimal(item, "sum") for item in values), start=Decimal(0))


def count(value: ComputationValue) -> Decimal:
    return Decimal(len(require_collection(value, "count")))


def minimum(value: ComputationValue) -> Decimal:
    values = require_collection(value, "min")
    if not values:
        raise PrimitiveExecutionError("min requires a non-empty collection")
    return min(require_decimal(item, "min") for item in values)


def maximum(value: ComputationValue) -> Decimal:
    values = require_collection(value, "max")
    if not values:
        raise PrimitiveExecutionError("max requires a non-empty collection")
    return max(require_decimal(item, "max") for item in values)


def equal(left: ComputationValue, right: ComputationValue) -> bool:
    return left == right


def greater_than(left: ComputationValue, right: ComputationValue) -> bool:
    return require_decimal(left, "greater_than") > require_decimal(right, "greater_than")


def less_than(left: ComputationValue, right: ComputationValue) -> bool:
    return require_decimal(left, "less_than") < require_decimal(right, "less_than")


def logical_and(left: ComputationValue, right: ComputationValue) -> bool:
    return require_boolean(left, "and") and require_boolean(right, "and")


def logical_or(left: ComputationValue, right: ComputationValue) -> bool:
    return require_boolean(left, "or") or require_boolean(right, "or")


def logical_not(value: ComputationValue) -> bool:
    return not require_boolean(value, "not")


def take(value: ComputationValue, amount: ComputationValue) -> list[ComputationValue]:
    values = require_collection(value, "take")
    decimal_amount = require_decimal(amount, "take")
    if decimal_amount != decimal_amount.to_integral_value() or decimal_amount < 0:
        raise PrimitiveExecutionError("take requires a non-negative integer amount")
    return values[: int(decimal_amount)]


def filter_values(
    value: ComputationValue,
    predicate: Callable[[ComputationValue, int], ComputationValue],
) -> list[ComputationValue]:
    values = require_collection(value, "filter")
    return [
        item
        for index, item in enumerate(values)
        if require_boolean(predicate(item, index), "filter")
    ]


def group_by(
    value: ComputationValue,
    key: Callable[[ComputationValue, int], ComputationValue],
) -> list[ComputationValue]:
    values = require_collection(value, "group_by")
    groups: list[tuple[ComputationValue, list[ComputationValue]]] = []
    for index, item in enumerate(values):
        item_key = key(item, index)
        matching = next((group for group in groups if group[0] == item_key), None)
        if matching is None:
            groups.append((item_key, [item]))
        else:
            matching[1].append(item)
    return [{"key": group_key, "items": items} for group_key, items in groups]


def sort_values(
    value: ComputationValue,
    key: Callable[[ComputationValue, int], ComputationValue],
    descending: bool,
) -> list[ComputationValue]:
    values = require_collection(value, "sort")
    decorated = [(item, key(item, index)) for index, item in enumerate(values)]
    key_types = {type(item_key) for _, item_key in decorated}
    if not key_types or key_types == {Decimal}:
        ordered = sorted(
            decorated,
            key=lambda pair: cast(Decimal, pair[1]),
            reverse=descending,
        )
    elif key_types == {str}:
        ordered = sorted(
            decorated,
            key=lambda pair: cast(str, pair[1]),
            reverse=descending,
        )
    elif key_types == {bool}:
        ordered = sorted(
            decorated,
            key=lambda pair: cast(bool, pair[1]),
            reverse=descending,
        )
    else:
        raise PrimitiveExecutionError("sort keys must have one scalar type")
    return [item for item, _ in ordered]


def distinct(
    value: ComputationValue,
    key: Callable[[ComputationValue, int], ComputationValue],
) -> list[ComputationValue]:
    values = require_collection(value, "distinct")
    result: list[ComputationValue] = []
    seen: list[ComputationValue] = []
    for index, item in enumerate(values):
        item_key = key(item, index)
        if item_key not in seen:
            seen.append(item_key)
            result.append(item)
    return result

from collections.abc import Awaitable, Callable
from typing import NotRequired

from typing_extensions import TypedDict

from reasoning.core_models import ComputationIntent, CoreVerificationResult
from reasoning.retrieval.models import RetrievalSearchResult

from .models import (
    ComputationPlan,
    ComputationPlanningResult,
    ComputationResult,
    Operand,
    OperandBindingResult,
)
from .services import ComputationPlanningService, ComputationService, OperandBindingService


class OperandBindingNodeInput(TypedDict):
    computation_intent: ComputationIntent
    retrieval_results: list[RetrievalSearchResult]


class OperandBindingNodeOutput(TypedDict):
    operand_binding: OperandBindingResult
    operands: tuple[Operand, ...]


class ComputationPlanningNodeInput(TypedDict):
    question: str
    operands: tuple[Operand, ...]
    core_verification: NotRequired[CoreVerificationResult]


class ComputationPlanningNodeOutput(TypedDict):
    computation_planning: ComputationPlanningResult


class ComputationExecutionNodeInput(TypedDict):
    computation_planning: ComputationPlanningResult
    operands: tuple[Operand, ...]
    computation_attempts: NotRequired[int]


class ComputationExecutionNodeOutput(TypedDict):
    computation_result: ComputationResult
    computation_attempts: int


def create_operand_binding_node(
    service: OperandBindingService,
) -> Callable[[OperandBindingNodeInput], Awaitable[OperandBindingNodeOutput]]:
    async def node(state: OperandBindingNodeInput) -> OperandBindingNodeOutput:
        binding = await service.bind(
            intent=state["computation_intent"],
            retrieval_results=tuple(state["retrieval_results"]),
        )
        return {"operand_binding": binding, "operands": binding.operands}

    return node


def create_computation_planning_node(
    service: ComputationPlanningService,
) -> Callable[[ComputationPlanningNodeInput], Awaitable[ComputationPlanningNodeOutput]]:
    async def node(state: ComputationPlanningNodeInput) -> ComputationPlanningNodeOutput:
        previous_verification = state.get("core_verification")
        feedback = previous_verification.issues if previous_verification else ()
        planning = await service.plan(
            question=state["question"],
            operands=state["operands"],
            feedback=feedback,
        )
        return {"computation_planning": planning}

    return node


def create_computation_execution_node(
    service: ComputationService,
) -> Callable[[ComputationExecutionNodeInput], ComputationExecutionNodeOutput]:
    def node(state: ComputationExecutionNodeInput) -> ComputationExecutionNodeOutput:
        plan = state["computation_planning"].plan
        if not isinstance(plan, ComputationPlan):
            raise ValueError("computation execution requires a supported plan")
        return {
            "computation_result": service.compute(plan, state["operands"]),
            "computation_attempts": state.get("computation_attempts", 0) + 1,
        }

    return node

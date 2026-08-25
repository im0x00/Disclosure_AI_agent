from collections.abc import Awaitable, Callable
from typing import NotRequired

from typing_extensions import TypedDict

from reasoning.core_models import ComputationIntent, CoreVerificationResult

from .models import QueryUnderstanding
from .services import QueryUnderstandingService


class QueryUnderstandingNodeInput(TypedDict):
    question: str
    understanding_attempts: NotRequired[int]
    core_verification: NotRequired[CoreVerificationResult]


class QueryUnderstandingNodeOutput(TypedDict):
    query_understanding: QueryUnderstanding
    computation_intent: ComputationIntent | None
    understanding_attempts: int


def create_query_safety_gate_node() -> None: ...


def create_query_understanding_node(
    service: QueryUnderstandingService,
) -> Callable[
    [QueryUnderstandingNodeInput],
    Awaitable[QueryUnderstandingNodeOutput],
]:

    async def node(
        state: QueryUnderstandingNodeInput,
    ) -> QueryUnderstandingNodeOutput:

        previous_verification = state.get("core_verification")
        feedback = previous_verification.issues if previous_verification else ()
        result = await service.understand(
            question=state["question"],
            feedback=feedback,
        )

        return {
            "query_understanding": result,
            "computation_intent": result.computation_intent,
            "understanding_attempts": state.get("understanding_attempts", 0) + 1,
        }

    return node

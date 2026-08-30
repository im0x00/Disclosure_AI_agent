from collections.abc import Awaitable, Callable
from typing import NotRequired

from typing_extensions import TypedDict

from reasoning.core.core_models import ComputationIntent, CoreVerificationResult

from .models import QuerySafetyResult, QueryUnderstanding
from .services import QuerySafetyGuardService, QueryUnderstandingService


class QuerySafetyGuardNodeInput(TypedDict):
    question: str


class QuerySafetyGuardNodeOutput(TypedDict):
    query_safety: QuerySafetyResult


class QueryUnderstandingNodeInput(TypedDict):
    question: str
    understanding_attempts: NotRequired[int]
    core_verification: NotRequired[CoreVerificationResult]
    clarification_answers: NotRequired[tuple[str, ...]]


class QueryUnderstandingNodeOutput(TypedDict):
    query_understanding: QueryUnderstanding
    computation_intent: ComputationIntent | None
    understanding_attempts: int


def create_query_safety_guard_node(
    service: QuerySafetyGuardService,
) -> Callable[
    [QuerySafetyGuardNodeInput],
    Awaitable[QuerySafetyGuardNodeOutput],
]:
    async def node(
        state: QuerySafetyGuardNodeInput,
    ) -> QuerySafetyGuardNodeOutput:
        result = await service.validate_query_safety(state["question"])
        return {"query_safety": result}

    return node


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
            clarification_answers=state.get("clarification_answers", ()),
        )

        return {
            "query_understanding": result,
            "computation_intent": result.computation_intent,
            "understanding_attempts": state.get("understanding_attempts", 0) + 1,
        }

    return node

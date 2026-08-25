# reasoning/generate_answer/nodes.py
from collections.abc import Awaitable, Callable
from typing import NotRequired

from typing_extensions import (
    TypedDict,
)

from reasoning.computing.models import ComputationResult
from reasoning.core_models import ComputationIntent, CoreVerificationResult
from reasoning.query_understanding.models import (
    QueryUnderstanding,
)
from reasoning.retrieval.models import (
    RetrievalSearchResult,
)

from .models import (
    AnswerVerificationResult,
    CannotAnswerResponse,
    Response,
)
from .services import ResponseGenerationService


class ClarificationNodeInput(TypedDict):
    query_understanding: QueryUnderstanding


class FinalResponseNodeInput(TypedDict):
    query_understanding: QueryUnderstanding

    retrieval_results: list[RetrievalSearchResult]
    computation_intent: NotRequired[ComputationIntent | None]
    computation_result: NotRequired[ComputationResult]


class ResponseNodeOutput(TypedDict):
    response: Response


class CannotAnswerNodeInput(TypedDict):
    core_verification: CoreVerificationResult


class AnswerVerificationNodeInput(TypedDict):
    response: Response


class AnswerVerificationNodeOutput(TypedDict):
    answer_verification: AnswerVerificationResult


def create_clarification_node(
    service: ResponseGenerationService,
) -> Callable[
    [ClarificationNodeInput],
    Awaitable[ResponseNodeOutput],
]:

    async def node(
        state: ClarificationNodeInput,
    ) -> ResponseNodeOutput:

        response = await service.clarify(state["query_understanding"])

        return {"response": response}

    return node


def create_final_answer_node(
    service: ResponseGenerationService,
) -> Callable[
    [FinalResponseNodeInput],
    Awaitable[ResponseNodeOutput],
]:

    async def node(
        state: FinalResponseNodeInput,
    ) -> ResponseNodeOutput:

        computation_result = (
            state.get("computation_result") if state.get("computation_intent") is not None else None
        )
        response = await service.answer(
            understanding=state["query_understanding"],
            retrieval_results=state["retrieval_results"],
            computation_result=computation_result,
        )

        return {"response": response}

    return node


def create_cannot_answer_node() -> Callable[[CannotAnswerNodeInput], ResponseNodeOutput]:
    def node(state: CannotAnswerNodeInput) -> ResponseNodeOutput:
        reasons = [issue.reason for issue in state["core_verification"].issues]
        response = CannotAnswerResponse(
            type="cannot_answer",
            main_text="The supplied disclosures do not support a reliable answer.",
            reasons=reasons or ["No answerable evidence path remains."],
        )
        return {"response": response}

    return node


def create_answer_verification_node() -> Callable[
    [AnswerVerificationNodeInput], AnswerVerificationNodeOutput
]:
    """Skeleton postcondition; semantic claim verification is intentionally deferred."""

    def node(_: AnswerVerificationNodeInput) -> AnswerVerificationNodeOutput:
        return {"answer_verification": AnswerVerificationResult()}

    return node

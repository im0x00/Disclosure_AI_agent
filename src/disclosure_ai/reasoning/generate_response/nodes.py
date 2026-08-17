# reasoning/generate_response/nodes.py
from collections.abc import Awaitable, Callable
from typing import NotRequired

from typing_extensions import (
    TypedDict,
)

from disclosure_ai.reasoning.query_understanding.models import (
    QueryUnderstanding,
)
from disclosure_ai.reasoning.retrieval.models import (
    RetrievalSearchResult,
)

from .models import Response
from .services import ResponseGenerationService


class ClarificationNodeInput(TypedDict):
    query_understanding: QueryUnderstanding


class FinalResponseNodeInput(TypedDict):
    query_understanding: QueryUnderstanding

    retrieval_results: NotRequired[list[RetrievalSearchResult]]


class ResponseNodeOutput(TypedDict):
    response: Response


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


def create_final_response_node(
    service: ResponseGenerationService,
) -> Callable[
    [FinalResponseNodeInput],
    Awaitable[ResponseNodeOutput],
]:

    async def node(
        state: FinalResponseNodeInput,
    ) -> ResponseNodeOutput:

        response = await service.answer(
            understanding=state["query_understanding"],
            retrieval_results=state.get(
                "retrieval_results",
                [],
            ),
        )

        return {"response": response}

    return node

from collections.abc import Awaitable, Callable

from typing_extensions import TypedDict

from .models import QueryUnderstanding
from .services import QueryUnderstandingService


class QueryUnderstandingNodeInput(TypedDict):
    question: str


class QueryUnderstandingNodeOutput(TypedDict):
    query_understanding: QueryUnderstanding


def create_query_understanding_node(
    service: QueryUnderstandingService,
) -> Callable[
    [QueryUnderstandingNodeInput],
    Awaitable[QueryUnderstandingNodeOutput],
]:

    async def node(
        state: QueryUnderstandingNodeInput,
    ) -> QueryUnderstandingNodeOutput:

        result = await service.understand(question=state["question"])

        return {"query_understanding": result}

    return node

# reasoning/retrieval/nodes.py
from collections.abc import Awaitable, Callable
from typing import NotRequired

from typing_extensions import TypedDict

from reasoning.core.core_models import CoreVerificationResult
from reasoning.query_understanding.models import (
    QueryUnderstanding,
)

from .models import (
    RetrievalFrame,
    RetrievalSearchResult,
)
from .services import RetrievalService


class RetrievalPlanInput(TypedDict):
    query_understanding: QueryUnderstanding
    core_verification: NotRequired[CoreVerificationResult]


class RetrievalPlanOutput(TypedDict):
    retrieval_frame: RetrievalFrame


class RetrievalSearchInput(TypedDict):
    retrieval_frame: RetrievalFrame
    retrieval_attempts: NotRequired[int]


class RetrievalSearchOutput(TypedDict):
    retrieval_results: list[RetrievalSearchResult]
    retrieval_attempts: int


def create_retrieval_plan_node(
    service: RetrievalService,
) -> Callable[[RetrievalPlanInput], Awaitable[RetrievalPlanOutput]]:

    async def node(
        state: RetrievalPlanInput,
    ) -> RetrievalPlanOutput:

        verification = state.get("core_verification")
        frame = await service.plan(
            understanding=state["query_understanding"],
            feedback=verification.issues if verification is not None else (),
        )

        return {"retrieval_frame": frame}

    return node


def create_retrieval_search_node(
    service: RetrievalService,
) -> Callable[[RetrievalSearchInput], Awaitable[RetrievalSearchOutput]]:

    async def node(
        state: RetrievalSearchInput,
    ) -> RetrievalSearchOutput:

        results = await service.search(frame=state["retrieval_frame"])

        return {
            "retrieval_results": results,
            "retrieval_attempts": state.get("retrieval_attempts", 0) + 1,
        }

    return node

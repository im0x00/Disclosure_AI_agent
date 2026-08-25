# reasoning/generate_answer/service.py

from langchain_core.language_models import BaseChatModel

from reasoning.computing.models import ComputationResult
from reasoning.query_understanding.models import (
    QueryUnderstanding,
)
from reasoning.retrieval.models import (
    RetrievalSearchResult,
)

from .models import (
    ClarificationResponse,
    FinalResponse,
)


class ResponseGenerationService:
    def __init__(
        self,
        llm: BaseChatModel,
    ):
        self.llm = llm

    async def clarify(
        self,
        understanding: QueryUnderstanding,
    ) -> ClarificationResponse:

        raise NotImplementedError

    async def answer(
        self,
        understanding: QueryUnderstanding,
        retrieval_results: list[RetrievalSearchResult],
        computation_result: ComputationResult | None = None,
    ) -> FinalResponse:

        raise NotImplementedError

# reasoning/generate_response/service.py

from langchain_core.language_models import BaseChatModel

from disclosure_ai.reasoning.query_understanding.models import (
    QueryUnderstanding,
)
from disclosure_ai.reasoning.retrieval.models import (
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
    ) -> FinalResponse:

        raise NotImplementedError

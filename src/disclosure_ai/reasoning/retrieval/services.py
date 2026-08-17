# reasoning/retrieval/services.py

from langchain_core.language_models import BaseChatModel

from disclosure_ai.reasoning.query_understanding.models import (
    QueryUnderstanding,
)

from .models import (
    RetrievalFrame,
    RetrievalSearchResult,
)


class RetrievalService:
    def __init__(
        self,
        llm: BaseChatModel,
    ):
        self.llm = llm

    async def plan(
        self,
        understanding: QueryUnderstanding,
    ) -> RetrievalFrame:
        """
        ContextPoint를 보고 EvidenceTarget을 생성한다.
        """

        raise NotImplementedError

    async def search(
        self,
        frame: RetrievalFrame,
    ) -> list[RetrievalSearchResult]:
        """
        EvidenceTarget마다 실제 corpus를 탐색한다.
        """

        raise NotImplementedError

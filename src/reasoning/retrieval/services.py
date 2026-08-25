import asyncio
import json
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from reasoning.core_models import VerificationIssue
from reasoning.query_understanding.models import (
    QueryUnderstanding,
)

from .models import (
    EvidenceTarget,
    RetrievalFrame,
    RetrievalSearchResult,
    RetrievedEvidence,
)


class RetrievalSearchBackend(Protocol):
    async def search(self, target: EvidenceTarget) -> list[RetrievedEvidence]: ...


class _RetrievalPlan(BaseModel):
    evidence_targets: list[EvidenceTarget] = Field(default_factory=list)


class RetrievalService:
    def __init__(
        self,
        llm: BaseChatModel,
        search_backend: RetrievalSearchBackend,
    ) -> None:
        self.llm = llm
        self.search_backend = search_backend

    async def plan(
        self,
        understanding: QueryUnderstanding,
        feedback: tuple[VerificationIssue, ...] = (),
    ) -> RetrievalFrame:
        planner = self.llm.with_structured_output(_RetrievalPlan)
        payload = {
            "query_understanding": understanding.model_dump(mode="json"),
            "verification_feedback": [item.model_dump(mode="json") for item in feedback],
        }
        raw_plan = await planner.ainvoke(
            [
                SystemMessage(
                    content=(
                        "Create only the evidence targets needed to answer the query. "
                        "Use verification feedback to repair a previous retrieval plan."
                    )
                ),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            ]
        )
        plan = _RetrievalPlan.model_validate(raw_plan)
        return RetrievalFrame(
            query_understanding=understanding,
            evidence_targets=plan.evidence_targets,
        )

    async def search(
        self,
        frame: RetrievalFrame,
    ) -> list[RetrievalSearchResult]:
        search_results = await asyncio.gather(
            *(self.search_backend.search(target) for target in frame.evidence_targets)
        )
        return [
            RetrievalSearchResult(target=target, search_results=list(results))
            for target, results in zip(
                frame.evidence_targets,
                search_results,
                strict=True,
            )
        ]

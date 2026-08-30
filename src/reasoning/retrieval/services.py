import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from reasoning.core.core_models import VerificationIssue
from reasoning.query_understanding.models import (
    QueryUnderstanding,
)

from .batch_service import RetrievalBatchService
from .errors import RetrievalDataError
from .models import (
    EvidenceTarget,
    RetrievalFrame,
    RetrievalSearchResult,
)


class _RetrievalPlan(BaseModel):
    evidence_targets: list[EvidenceTarget] = Field(default_factory=list)


class RetrievalService:
    def __init__(
        self,
        llm: BaseChatModel,
        batch_service: RetrievalBatchService,
    ) -> None:
        self.llm = llm
        self.batch_service = batch_service

    async def plan(
        self,
        understanding: QueryUnderstanding,
        feedback: tuple[VerificationIssue, ...] = (),
    ) -> RetrievalFrame:
        planner = self.llm.with_structured_output(
            _RetrievalPlan,
            method="json_schema",
        )
        payload = {
            "query_understanding": understanding.model_dump(mode="json"),
            "verification_feedback": [item.model_dump(mode="json") for item in feedback],
        }
        raw_plan = await planner.ainvoke(
            [
                SystemMessage(
                    content=(
                        "Create only the evidence targets needed to answer the query. "
                        "Copy supported_by exactly from query_understanding.contextual_points. "
                        "When computation_intent exists, create targets covering every required "
                        "operand_id and never invent an operand_id. "
                        "Use verification feedback to repair a previous retrieval plan."
                    )
                ),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            ]
        )
        plan = _RetrievalPlan.model_validate(raw_plan)
        self._validate_plan(understanding, plan)
        return RetrievalFrame(
            query_understanding=understanding,
            evidence_targets=plan.evidence_targets,
        )

    @staticmethod
    def _validate_plan(
        understanding: QueryUnderstanding,
        plan: _RetrievalPlan,
    ) -> None:
        if any(
            target.supported_by not in understanding.contextual_points
            for target in plan.evidence_targets
        ):
            raise RetrievalDataError("retrieval plan cites context outside QueryUnderstanding")

        intent = understanding.computation_intent
        allowed_operand_ids = (
            {item.operand_id for item in intent.required_operands} if intent is not None else set()
        )
        planned_operand_ids = {
            target.operand_id for target in plan.evidence_targets if target.operand_id is not None
        }
        if not planned_operand_ids.issubset(allowed_operand_ids):
            raise RetrievalDataError("retrieval plan contains an unknown operand_id")
        if intent is not None and planned_operand_ids != allowed_operand_ids:
            raise RetrievalDataError("retrieval plan must cover every required computation operand")

    async def search(
        self,
        frame: RetrievalFrame,
    ) -> list[RetrievalSearchResult]:
        batches = await self.batch_service.search(frame)
        return [
            RetrievalSearchResult(
                target=batch.request.target,
                search_results=list(batch.hits),
            )
            for batch in batches
        ]

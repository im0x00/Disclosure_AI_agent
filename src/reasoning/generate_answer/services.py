import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from reasoning.computing.models import ComputationResult
from reasoning.core.evidence_adapters import answer_evidence_payload
from reasoning.query_understanding.models import (
    QueryUnderstanding,
)
from reasoning.retrieval.models import (
    RetrievalSearchResult,
)

from .models import (
    AnswerClaim,
    AnswerVerificationIssue,
    ClarificationResponse,
    FinalResponse,
)

_ANSWER_PROMPT = """Write a concise answer using only the supplied evidence and computation.
Return atomic claims. Every factual claim must cite one or more supplied evidence references or set
uses_computation=true and copy the exact supplied computation value. Do not invent identifiers,
facts, values, or citations. Do not add uncited factual prose.
If answer_verification_feedback is present, repair every listed issue.
"""

_CLARIFICATION_PROMPT = """Ask one concise question that resolves the listed missing or ambiguous
context points. Do not answer the original question.
"""


class _FinalAnswerDraft(BaseModel):
    claims: tuple[AnswerClaim, ...] = Field(min_length=1)


class _ClarificationDraft(BaseModel):
    main_text: str = Field(min_length=1)


class ResponseGenerationService:
    def __init__(
        self,
        llm: BaseChatModel,
    ) -> None:
        self.llm = llm

    async def clarify(
        self,
        understanding: QueryUnderstanding,
    ) -> ClarificationResponse:
        generator = self.llm.with_structured_output(
            _ClarificationDraft,
            method="json_schema",
        )
        raw_result = await generator.ainvoke(
            [
                SystemMessage(content=_CLARIFICATION_PROMPT),
                HumanMessage(content=understanding.model_dump_json()),
            ]
        )
        draft = (
            raw_result
            if isinstance(raw_result, _ClarificationDraft)
            else _ClarificationDraft.model_validate(raw_result)
        )
        unresolved = [
            point
            for point in understanding.contextual_points
            if point.status.value in {"ambiguous", "missing"}
        ]
        return ClarificationResponse(
            type="clarification",
            main_text=draft.main_text,
            missing_context_keys=unresolved,
        )

    async def answer(
        self,
        understanding: QueryUnderstanding,
        retrieval_results: list[RetrievalSearchResult],
        computation_result: ComputationResult | None = None,
        feedback: tuple[AnswerVerificationIssue, ...] = (),
    ) -> FinalResponse:
        evidence_payload = answer_evidence_payload(retrieval_results)
        payload = {
            "query_understanding": understanding.model_dump(mode="json"),
            "evidence": evidence_payload,
            "computation": computation_result.model_dump(mode="json")
            if computation_result is not None
            else None,
            "answer_verification_feedback": [issue.model_dump(mode="json") for issue in feedback],
        }
        generator = self.llm.with_structured_output(
            _FinalAnswerDraft,
            method="json_schema",
        )
        raw_result = await generator.ainvoke(
            [
                SystemMessage(content=_ANSWER_PROMPT),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            ]
        )
        draft = (
            raw_result
            if isinstance(raw_result, _FinalAnswerDraft)
            else _FinalAnswerDraft.model_validate(raw_result)
        )
        return FinalResponse(
            type="final",
            main_text="\n".join(claim.text for claim in draft.claims),
            claims=draft.claims,
            evidences=retrieval_results,
            computation=computation_result,
        )

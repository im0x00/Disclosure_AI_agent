import asyncio
from typing import cast
from unittest.mock import Mock
from uuid import UUID

from langchain_core.language_models import BaseChatModel

from reasoning.core_models import (
    CoreVerificationResult,
    RetryPolicy,
    VerificationAction,
    VerificationIssue,
)
from reasoning.core_verification import CoreVerificationService
from reasoning.query_understanding.models import (
    ContextOrigin,
    ContextPoint,
    ContextStatus,
    QueryUnderstanding,
)
from reasoning.retrieval.models import EvidenceTarget, RetrievalSearchResult, RetrievedEvidence


def test_semantic_verifier_retries_a_concrete_misunderstanding_then_stops_at_budget() -> None:
    assessment = CoreVerificationResult(
        action=VerificationAction.RETRY_UNDERSTANDING,
        issues=(
            VerificationIssue(
                code="inferred_context_conflict",
                reason="evidence supports a different reporting scope",
            ),
        ),
    )
    runnable = _StructuredVerifier(assessment)
    llm = Mock(spec=BaseChatModel)
    llm.with_structured_output.return_value = runnable
    service = CoreVerificationService(
        cast(BaseChatModel, llm),
        retry_policy=RetryPolicy(max_understanding_attempts=2),
    )

    first = asyncio.run(_verify(service, understanding_attempts=1))
    exhausted = asyncio.run(_verify(service, understanding_attempts=2))

    assert first.action == VerificationAction.RETRY_UNDERSTANDING
    assert exhausted.action == VerificationAction.CANNOT_ANSWER
    assert exhausted.issues[-1].code == "retry_exhausted"


async def _verify(
    service: CoreVerificationService,
    *,
    understanding_attempts: int,
) -> CoreVerificationResult:
    point = ContextPoint(
        key="scope",
        status=ContextStatus.INFERRED,
        value="consolidated",
        origin=ContextOrigin.INFERRED,
    )
    evidence = RetrievedEvidence(
        document_id="doc",
        node_id=UUID("00000000-0000-0000-0000-000000000001"),
        node_type="cell",
        text="Separate-basis amount",
        source_path="raw/doc.xml",
        start_byte=0,
        end_byte=21,
    )
    return await service.verify(
        question="What is the amount?",
        understanding=QueryUnderstanding(
            question_raw="What is the amount?",
            intention="find amount",
            contextual_points=[point],
            needs_clarification=False,
        ),
        retrieval_results=(
            RetrievalSearchResult(
                target=EvidenceTarget(need="amount", supported_by=point),
                search_results=[evidence],
            ),
        ),
        computation_intent=None,
        operand_binding=None,
        computation_planning=None,
        computation_result=None,
        understanding_attempts=understanding_attempts,
        retrieval_attempts=1,
        computation_attempts=0,
    )


class _StructuredVerifier:
    def __init__(self, result: CoreVerificationResult) -> None:
        self.result = result

    async def ainvoke(self, _: object) -> CoreVerificationResult:
        return self.result

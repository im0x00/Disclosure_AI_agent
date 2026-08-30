import asyncio
from decimal import Decimal
from typing import cast
from unittest.mock import Mock

from langchain_core.language_models import BaseChatModel

from reasoning.computing.models import (
    ComputationPlan,
    ComputationResult,
    ComputationStatus,
    EvidenceReference,
    ReferenceExpression,
)
from reasoning.generate_answer.models import (
    AnswerClaim,
    AnswerVerificationStatus,
    FinalResponse,
)
from reasoning.generate_answer.nodes import create_answer_verification_node
from reasoning.generate_answer.services import ResponseGenerationService
from reasoning.query_understanding.models import (
    ContextPoint,
    ContextStatus,
    QueryUnderstanding,
)
from reasoning.retrieval.models import EvidenceTarget, RetrievalSearchResult
from tests.reasoning.retrieval_fixtures import retrieved_evidence


def test_response_generation_attaches_original_work_products() -> None:
    result, reference = _retrieval_result()
    runnable = _StructuredOutput(
        {
            "claims": [
                {
                    "text": "The disclosed amount is 10.",
                    "evidence_refs": [reference.model_dump(mode="json")],
                }
            ]
        }
    )
    llm = Mock(spec=BaseChatModel)
    llm.with_structured_output.return_value = runnable
    service = ResponseGenerationService(cast(BaseChatModel, llm))

    response = asyncio.run(service.answer(_understanding(), [result]))

    assert response.main_text == "The disclosed amount is 10."
    assert response.evidences == [result]
    assert response.claims[0].evidence_refs == (reference,)


def test_answer_verification_rejects_unknown_citation_and_wrong_computation_value() -> None:
    result, _ = _retrieval_result()
    unknown_reference = EvidenceReference(
        document_id="unknown",
        grain_id="9" * 64,
    )
    computation = ComputationResult(
        status=ComputationStatus.SUCCESS,
        plan=ComputationPlan(
            goal="amount",
            expression=ReferenceExpression(name="amount"),
        ),
        value=Decimal("10"),
    )
    response = FinalResponse(
        type="final",
        main_text="The amount is 11.",
        claims=(
            AnswerClaim(
                text="The amount is 11.",
                evidence_refs=(unknown_reference,),
                uses_computation=True,
                computed_value=Decimal("11"),
            ),
        ),
        evidences=[result],
        computation=computation,
    )

    output = create_answer_verification_node()({"response": response})

    verification = output["answer_verification"]
    assert verification.status == AnswerVerificationStatus.FAIL
    assert {issue.code for issue in verification.issues} == {
        "unknown_evidence_reference",
        "computation_value_mismatch",
    }


class _StructuredOutput:
    def __init__(self, result: object) -> None:
        self.result = result

    async def ainvoke(self, _: object) -> object:
        return self.result


def _understanding() -> QueryUnderstanding:
    return QueryUnderstanding(
        question_raw="What is the amount?",
        intention="find amount",
        contextual_points=[
            ContextPoint(key="company", status=ContextStatus.KNOWN, value="Example Corp")
        ],
        needs_clarification=False,
    )


def _retrieval_result() -> tuple[RetrievalSearchResult, EvidenceReference]:
    point = _understanding().contextual_points[0]
    evidence = retrieved_evidence(
        document_id="doc",
        grain_id="1" * 64,
        text="The disclosed amount is 10.",
    )
    return (
        RetrievalSearchResult(
            target=EvidenceTarget(need="amount", supported_by=point),
            search_results=[evidence],
        ),
        EvidenceReference(document_id=evidence.document_id, grain_id=evidence.grain_id),
    )

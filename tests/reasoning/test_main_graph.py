import asyncio
from decimal import Decimal
from typing import Any, cast
from unittest.mock import Mock
from uuid import UUID

from langchain_core.language_models import BaseChatModel

from reasoning.computing.models import (
    ComputationPlan,
    ComputationPlanningResult,
    EvidenceReference,
    Operand,
    OperandBindingResult,
    OperationExpression,
    Primitive,
    ReferenceExpression,
)
from reasoning.computing.services import (
    ComputationPlanningService,
    ComputationService,
    OperandBindingService,
)
from reasoning.core_models import (
    ComputationIntent,
    CoreVerificationResult,
    OperandRequirement,
    RetryPolicy,
    VerificationAction,
    VerificationIssue,
)
from reasoning.core_verification import CoreVerificationService
from reasoning.generate_answer.models import CannotAnswerResponse, FinalResponse
from reasoning.generate_answer.services import ResponseGenerationService
from reasoning.graph import GraphDependencies, build_graph
from reasoning.query_understanding.models import (
    ContextPoint,
    ContextStatus,
    QueryUnderstanding,
)
from reasoning.query_understanding.services import QueryUnderstandingService
from reasoning.retrieval.models import (
    EvidenceTarget,
    RetrievalFrame,
    RetrievalSearchResult,
    RetrievedEvidence,
)
from reasoning.retrieval.services import RetrievalService


def test_computation_path_retrieves_binds_computes_verifies_and_answers() -> None:
    intent = ComputationIntent(
        goal="divide left by right",
        required_operands=(
            OperandRequirement(operand_id="left", description="left amount"),
            OperandRequirement(operand_id="right", description="right amount"),
        ),
    )
    understanding = _understanding(computation_intent=intent)
    retrieval = _RetrievalFake(understanding, with_evidence=True)
    binder = _BindingFake(retrieval.evidence)
    planner = _PlanningFake()
    verifier = _VerificationFake(VerificationAction.PASS)
    answer = _AnswerFake()
    graph = build_graph(
        GraphDependencies(
            query_understanding=cast(
                QueryUnderstandingService,
                _UnderstandingFake(understanding),
            ),
            retrieval=cast(RetrievalService, retrieval),
            operand_binding=cast(OperandBindingService, binder),
            computation_planning=cast(ComputationPlanningService, planner),
            computation=ComputationService(),
            core_verification=cast(CoreVerificationService, verifier),
            answer_generation=cast(ResponseGenerationService, answer),
        )
    )

    output = asyncio.run(graph.ainvoke({"question": "What is the ratio?"}))

    response = output["response"]
    assert isinstance(response, FinalResponse)
    assert response.computation is not None
    assert response.computation.value == Decimal("5")
    assert binder.calls == 1
    assert planner.calls == 1
    assert verifier.calls == 1
    assert answer.answer_calls == 1


def test_missing_evidence_reuses_retrieval_until_budget_then_returns_cannot_answer() -> None:
    understanding = _understanding(computation_intent=None)
    retrieval = _RetrievalFake(understanding, with_evidence=False)
    llm = Mock(spec=BaseChatModel)
    verifier = CoreVerificationService(
        llm=cast(BaseChatModel, llm),
        retry_policy=RetryPolicy(max_retrieval_attempts=2),
    )
    graph = build_graph(
        GraphDependencies(
            query_understanding=cast(
                QueryUnderstandingService,
                _UnderstandingFake(understanding),
            ),
            retrieval=cast(RetrievalService, retrieval),
            operand_binding=cast(OperandBindingService, _UnexpectedService()),
            computation_planning=cast(ComputationPlanningService, _UnexpectedService()),
            computation=ComputationService(),
            core_verification=verifier,
            answer_generation=cast(ResponseGenerationService, _AnswerFake()),
        )
    )

    output = asyncio.run(graph.ainvoke({"question": "Find unavailable evidence"}))

    assert isinstance(output["response"], CannotAnswerResponse)
    assert retrieval.search_calls == 2
    assert len(retrieval.feedback_seen) == 2
    assert retrieval.feedback_seen[0] == ()
    assert retrieval.feedback_seen[1][0].code == "missing_evidence"


def test_inferred_context_conflict_retries_understanding_with_feedback() -> None:
    understanding = _understanding(computation_intent=None)
    understanding_service = _UnderstandingFake(understanding)
    retrieval = _RetrievalFake(understanding, with_evidence=True)
    issue = VerificationIssue(
        code="inferred_context_conflict",
        reason="evidence supports a different reporting scope",
    )
    verifier = _VerificationSequenceFake(
        CoreVerificationResult(
            action=VerificationAction.RETRY_UNDERSTANDING,
            issues=(issue,),
        ),
        CoreVerificationResult(action=VerificationAction.PASS),
    )
    graph = build_graph(
        GraphDependencies(
            query_understanding=cast(QueryUnderstandingService, understanding_service),
            retrieval=cast(RetrievalService, retrieval),
            operand_binding=cast(OperandBindingService, _UnexpectedService()),
            computation_planning=cast(ComputationPlanningService, _UnexpectedService()),
            computation=ComputationService(),
            core_verification=cast(CoreVerificationService, verifier),
            answer_generation=cast(ResponseGenerationService, _AnswerFake()),
        )
    )

    output = asyncio.run(graph.ainvoke({"question": "Which reporting scope?"}))

    assert isinstance(output["response"], FinalResponse)
    assert understanding_service.feedback_seen == [(), (issue,)]
    assert retrieval.search_calls == 2


class _UnderstandingFake:
    def __init__(self, result: QueryUnderstanding) -> None:
        self.result = result
        self.feedback_seen: list[tuple[VerificationIssue, ...]] = []

    async def understand(
        self,
        question: str,
        feedback: tuple[VerificationIssue, ...] = (),
    ) -> QueryUnderstanding:
        del question
        self.feedback_seen.append(feedback)
        return self.result


class _RetrievalFake:
    def __init__(self, understanding: QueryUnderstanding, *, with_evidence: bool) -> None:
        self.understanding = understanding
        self.with_evidence = with_evidence
        self.search_calls = 0
        self.feedback_seen: list[tuple[VerificationIssue, ...]] = []
        self.evidence = (
            RetrievedEvidence(
                document_id="doc-left",
                node_id=UUID("00000000-0000-0000-0000-000000000001"),
                node_type="cell",
                text="Left amount is 10.",
                source_path="raw/left.xml",
                start_byte=0,
                end_byte=18,
            ),
            RetrievedEvidence(
                document_id="doc-right",
                node_id=UUID("00000000-0000-0000-0000-000000000002"),
                node_type="cell",
                text="Right amount is 2.",
                source_path="raw/right.xml",
                start_byte=0,
                end_byte=18,
            ),
        )

    async def plan(self, understanding, feedback=()):  # type: ignore[no-untyped-def]
        self.feedback_seen.append(feedback)
        point = understanding.contextual_points[0]
        targets = [
            EvidenceTarget(need="left amount", supported_by=point, operand_id="left"),
            EvidenceTarget(need="right amount", supported_by=point, operand_id="right"),
        ]
        if understanding.computation_intent is None:
            targets = [EvidenceTarget(need="requested fact", supported_by=point)]
        return RetrievalFrame(query_understanding=understanding, evidence_targets=targets)

    async def search(self, frame: RetrievalFrame) -> list[RetrievalSearchResult]:
        self.search_calls += 1
        results: list[RetrievalSearchResult] = []
        for index, target in enumerate(frame.evidence_targets):
            evidence = [self.evidence[index]] if self.with_evidence else []
            results.append(RetrievalSearchResult(target=target, search_results=evidence))
        return results


class _BindingFake:
    def __init__(self, evidence: tuple[RetrievedEvidence, ...]) -> None:
        self.evidence = evidence
        self.calls = 0

    async def bind(self, intent, retrieval_results):  # type: ignore[no-untyped-def]
        del intent, retrieval_results
        self.calls += 1
        return OperandBindingResult(
            operands=(
                Operand(
                    operand_id="left",
                    value=Decimal("10"),
                    evidence_refs=(
                        EvidenceReference(
                            document_id=self.evidence[0].document_id,
                            node_id=self.evidence[0].node_id,
                        ),
                    ),
                ),
                Operand(
                    operand_id="right",
                    value=Decimal("2"),
                    evidence_refs=(
                        EvidenceReference(
                            document_id=self.evidence[1].document_id,
                            node_id=self.evidence[1].node_id,
                        ),
                    ),
                ),
            )
        )


class _PlanningFake:
    def __init__(self) -> None:
        self.calls = 0

    async def plan(self, question, operands, feedback=()):  # type: ignore[no-untyped-def]
        del question, operands, feedback
        self.calls += 1
        return ComputationPlanningResult(
            plan=ComputationPlan(
                goal="ratio",
                expression=OperationExpression(
                    op=Primitive.DIVIDE,
                    arguments=(
                        ReferenceExpression(name="left"),
                        ReferenceExpression(name="right"),
                    ),
                ),
            )
        )


class _VerificationFake:
    def __init__(self, action: VerificationAction) -> None:
        self.action = action
        self.calls = 0

    async def verify(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        self.calls += 1
        return CoreVerificationResult(action=self.action)


class _VerificationSequenceFake:
    def __init__(self, *results: CoreVerificationResult) -> None:
        self.results = list(results)

    async def verify(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return self.results.pop(0)


class _AnswerFake:
    def __init__(self) -> None:
        self.answer_calls = 0

    async def clarify(self, understanding):  # type: ignore[no-untyped-def]
        raise AssertionError(f"unexpected clarification: {understanding}")

    async def answer(
        self,
        understanding: QueryUnderstanding,
        retrieval_results: list[RetrievalSearchResult],
        computation_result: Any = None,
    ) -> FinalResponse:
        del understanding
        self.answer_calls += 1
        return FinalResponse(
            type="final",
            main_text="answer",
            evidences=retrieval_results,
            computation=computation_result,
        )


class _UnexpectedService:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"unexpected service call: {name}")


def _understanding(computation_intent: ComputationIntent | None) -> QueryUnderstanding:
    return QueryUnderstanding(
        question_raw="question",
        intention="answer the question",
        contextual_points=[
            ContextPoint(key="company", status=ContextStatus.KNOWN, value="Example Corp")
        ],
        needs_clarification=False,
        computation_intent=computation_intent,
    )

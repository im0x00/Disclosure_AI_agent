import asyncio
from decimal import Decimal
from typing import Any, cast
from unittest.mock import Mock

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

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
from reasoning.core.core_graph import GraphDependencies, RuntimeNodeRetryPolicy, build_graph
from reasoning.core.core_models import (
    ComputationIntent,
    CoreVerificationResult,
    OperandRequirement,
    RetryPolicy,
    VerificationAction,
    VerificationIssue,
)
from reasoning.core.core_verification import CoreVerificationService
from reasoning.generate_answer.models import (
    AnswerClaim,
    AnswerVerificationIssue,
    CannotAnswerResponse,
    ClarificationResponse,
    FinalResponse,
)
from reasoning.generate_answer.services import ResponseGenerationService
from reasoning.query_understanding.models import (
    ContextPoint,
    ContextStatus,
    QuerySafetyResult,
    QueryUnderstanding,
)
from reasoning.query_understanding.services import (
    QuerySafetyGuardService,
    QueryUnderstandingService,
)
from reasoning.retrieval.models import (
    EvidenceTarget,
    RetrievalFrame,
    RetrievalSearchResult,
    RetrievedEvidence,
)
from reasoning.retrieval.services import RetrievalService
from tests.reasoning.retrieval_fixtures import retrieved_evidence


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
            query_safety=cast(QuerySafetyGuardService, _SafetyFake()),
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
            query_safety=cast(QuerySafetyGuardService, _SafetyFake()),
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
            query_safety=cast(QuerySafetyGuardService, _SafetyFake()),
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


def test_transient_node_failure_retries_twice_then_returns_cannot_answer() -> None:
    understanding_service = _TransientFailingUnderstandingFake()
    graph = build_graph(
        GraphDependencies(
            query_safety=cast(QuerySafetyGuardService, _SafetyFake()),
            query_understanding=cast(QueryUnderstandingService, understanding_service),
            retrieval=cast(RetrievalService, _UnexpectedService()),
            operand_binding=cast(OperandBindingService, _UnexpectedService()),
            computation_planning=cast(ComputationPlanningService, _UnexpectedService()),
            computation=ComputationService(),
            core_verification=cast(CoreVerificationService, _UnexpectedService()),
            answer_generation=cast(ResponseGenerationService, _AnswerFake()),
        ),
        runtime_retry_policy=RuntimeNodeRetryPolicy(base_delay_seconds=0),
    )

    output = asyncio.run(graph.ainvoke({"question": "What happened?"}))

    assert isinstance(output["response"], CannotAnswerResponse)
    assert understanding_service.calls == 2
    assert output["response"].reasons == ["query_understanding failed after 2 attempts"]


def test_non_transient_node_failure_is_not_retried() -> None:
    understanding_service = _NonTransientFailingUnderstandingFake()
    graph = build_graph(
        GraphDependencies(
            query_safety=cast(QuerySafetyGuardService, _SafetyFake()),
            query_understanding=cast(QueryUnderstandingService, understanding_service),
            retrieval=cast(RetrievalService, _UnexpectedService()),
            operand_binding=cast(OperandBindingService, _UnexpectedService()),
            computation_planning=cast(ComputationPlanningService, _UnexpectedService()),
            computation=ComputationService(),
            core_verification=cast(CoreVerificationService, _UnexpectedService()),
            answer_generation=cast(ResponseGenerationService, _AnswerFake()),
        ),
        runtime_retry_policy=RuntimeNodeRetryPolicy(base_delay_seconds=0),
    )

    output = asyncio.run(graph.ainvoke({"question": "What happened?"}))

    assert isinstance(output["response"], CannotAnswerResponse)
    assert understanding_service.calls == 1
    assert output["response"].reasons == ["query_understanding failed after 1 attempts"]


def test_answer_verification_feedback_repairs_answer_once() -> None:
    understanding = _understanding(computation_intent=None)
    retrieval = _RetrievalFake(understanding, with_evidence=True)
    answer = _RepairingAnswerFake()
    graph = build_graph(
        GraphDependencies(
            query_safety=cast(QuerySafetyGuardService, _SafetyFake()),
            query_understanding=cast(
                QueryUnderstandingService,
                _UnderstandingFake(understanding),
            ),
            retrieval=cast(RetrievalService, retrieval),
            operand_binding=cast(OperandBindingService, _UnexpectedService()),
            computation_planning=cast(ComputationPlanningService, _UnexpectedService()),
            computation=ComputationService(),
            core_verification=cast(
                CoreVerificationService,
                _VerificationFake(VerificationAction.PASS),
            ),
            answer_generation=cast(ResponseGenerationService, answer),
        )
    )

    output = asyncio.run(graph.ainvoke({"question": "What is the amount?"}))

    assert isinstance(output["response"], FinalResponse)
    assert answer.calls == 2
    assert answer.feedback_codes == [(), ("unknown_evidence_reference",)]


def test_clarification_interrupt_resumes_the_same_run() -> None:
    clarification_needed = QueryUnderstanding(
        question_raw="What is the amount?",
        intention="find amount",
        contextual_points=[
            ContextPoint(key="company", status=ContextStatus.MISSING, critical=True)
        ],
        needs_clarification=True,
    )
    resolved = _understanding(computation_intent=None)
    understanding_service = _UnderstandingSequenceFake(clarification_needed, resolved)
    retrieval = _RetrievalFake(resolved, with_evidence=True)
    graph = build_graph(
        GraphDependencies(
            query_safety=cast(QuerySafetyGuardService, _SafetyFake()),
            query_understanding=cast(QueryUnderstandingService, understanding_service),
            retrieval=cast(RetrievalService, retrieval),
            operand_binding=cast(OperandBindingService, _UnexpectedService()),
            computation_planning=cast(ComputationPlanningService, _UnexpectedService()),
            computation=ComputationService(),
            core_verification=cast(
                CoreVerificationService,
                _VerificationFake(VerificationAction.PASS),
            ),
            answer_generation=cast(ResponseGenerationService, _ClarifyingAnswerFake()),
        ),
        checkpointer=InMemorySaver(),
    )
    config: RunnableConfig = {"configurable": {"thread_id": "clarification-test"}}
    resume_command: Command[Any] = Command(resume={"answer": "Example Corp"})

    interrupted = asyncio.run(graph.ainvoke({"question": "What is the amount?"}, config=config))
    output = asyncio.run(graph.ainvoke(resume_command, config=config))

    assert "__interrupt__" in interrupted
    assert isinstance(output["response"], FinalResponse)
    assert understanding_service.clarification_answers_seen == [(), ("Example Corp",)]


class _UnderstandingFake:
    def __init__(self, result: QueryUnderstanding) -> None:
        self.result = result
        self.feedback_seen: list[tuple[VerificationIssue, ...]] = []

    async def understand(
        self,
        question: str,
        feedback: tuple[VerificationIssue, ...] = (),
        clarification_answers: tuple[str, ...] = (),
    ) -> QueryUnderstanding:
        del question, clarification_answers
        self.feedback_seen.append(feedback)
        return self.result


class _SafetyFake:
    async def validate_query_safety(self, question: str) -> QuerySafetyResult:
        del question
        return QuerySafetyResult(is_safe=True, reason="ordinary disclosure question")


class _TransientFailingUnderstandingFake:
    def __init__(self) -> None:
        self.calls = 0

    async def understand(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        self.calls += 1
        raise TimeoutError("temporary model timeout")


class _NonTransientFailingUnderstandingFake:
    def __init__(self) -> None:
        self.calls = 0

    async def understand(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        self.calls += 1
        raise ValueError("invalid structured output")


class _UnderstandingSequenceFake:
    def __init__(self, *results: QueryUnderstanding) -> None:
        self.results = list(results)
        self.clarification_answers_seen: list[tuple[str, ...]] = []

    async def understand(
        self,
        question: str,
        feedback: tuple[VerificationIssue, ...] = (),
        clarification_answers: tuple[str, ...] = (),
    ) -> QueryUnderstanding:
        del question, feedback
        self.clarification_answers_seen.append(clarification_answers)
        return self.results.pop(0)


class _RetrievalFake:
    def __init__(self, understanding: QueryUnderstanding, *, with_evidence: bool) -> None:
        self.understanding = understanding
        self.with_evidence = with_evidence
        self.search_calls = 0
        self.feedback_seen: list[tuple[VerificationIssue, ...]] = []
        self.evidence = (
            retrieved_evidence(
                document_id="doc-left",
                grain_id="1" * 64,
                text="Left amount is 10.",
                target_id="target:left",
            ),
            retrieved_evidence(
                document_id="doc-right",
                grain_id="2" * 64,
                text="Right amount is 2.",
                target_id="target:right",
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
                            grain_id=self.evidence[0].grain_id,
                        ),
                    ),
                ),
                Operand(
                    operand_id="right",
                    value=Decimal("2"),
                    evidence_refs=(
                        EvidenceReference(
                            document_id=self.evidence[1].document_id,
                            grain_id=self.evidence[1].grain_id,
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
        feedback: tuple[AnswerVerificationIssue, ...] = (),
    ) -> FinalResponse:
        del understanding, feedback
        self.answer_calls += 1
        return FinalResponse(
            type="final",
            main_text="answer",
            claims=(
                AnswerClaim(
                    text="answer",
                    evidence_refs=(
                        EvidenceReference(
                            document_id=retrieval_results[0].search_results[0].document_id,
                            grain_id=retrieval_results[0].search_results[0].grain_id,
                        ),
                    ),
                    uses_computation=computation_result is not None,
                    computed_value=(
                        computation_result.value if computation_result is not None else None
                    ),
                ),
            ),
            evidences=retrieval_results,
            computation=computation_result,
        )


class _ClarifyingAnswerFake(_AnswerFake):
    async def clarify(self, understanding: QueryUnderstanding) -> ClarificationResponse:
        return ClarificationResponse(
            type="clarification",
            main_text="Which company?",
            missing_context_keys=understanding.contextual_points,
        )


class _RepairingAnswerFake(_AnswerFake):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0
        self.feedback_codes: list[tuple[str, ...]] = []

    async def answer(
        self,
        understanding: QueryUnderstanding,
        retrieval_results: list[RetrievalSearchResult],
        computation_result: Any = None,
        feedback: tuple[AnswerVerificationIssue, ...] = (),
    ) -> FinalResponse:
        del understanding, computation_result
        self.calls += 1
        self.feedback_codes.append(tuple(issue.code for issue in feedback))
        evidence = retrieval_results[0].search_results[0]
        reference = EvidenceReference(
            document_id=evidence.document_id if self.calls > 1 else "unknown",
            grain_id=evidence.grain_id,
        )
        return FinalResponse(
            type="final",
            main_text="answer",
            claims=(AnswerClaim(text="answer", evidence_refs=(reference,)),),
            evidences=retrieval_results,
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

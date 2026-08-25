import json
from collections.abc import Awaitable, Callable
from typing import NotRequired

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from typing_extensions import TypedDict

from reasoning.computing.models import (
    ComputationErrorCode,
    ComputationPlanningResult,
    ComputationResult,
    ComputationStatus,
    OperandBindingResult,
)
from reasoning.query_understanding.models import QueryUnderstanding
from reasoning.retrieval.models import RetrievalSearchResult

from .core_models import (
    ComputationIntent,
    CoreVerificationResult,
    RetryPolicy,
    VerificationAction,
    VerificationIssue,
)

_VERIFICATION_PROMPT = """
Decide whether the current work can support a grounded answer.
- Use retry_understanding only when the evidence supports a concrete alternative interpretation of
an inferred query context.
- Use retry_retrieval when an actionable evidence search remains.
- Use cannot_answer when the required fact is outside the supplied corpus, the evidence explicitly cannot
establish it, or no actionable retry remains.
- Use pass only when every requested conclusion is supported.

Do not treat user-provided constraints as disclosure evidence.
"""  # noqa: E501


class CoreVerificationService:
    def __init__(self, llm: BaseChatModel, retry_policy: RetryPolicy | None = None) -> None:
        self.llm = llm
        self.retry_policy = retry_policy or RetryPolicy()

    async def verify(
        self,
        *,
        question: str,
        understanding: QueryUnderstanding,
        retrieval_results: tuple[RetrievalSearchResult, ...],
        computation_intent: ComputationIntent | None,
        operand_binding: OperandBindingResult | None,
        computation_planning: ComputationPlanningResult | None,
        computation_result: ComputationResult | None,
        understanding_attempts: int,
        retrieval_attempts: int,
        computation_attempts: int,
    ) -> CoreVerificationResult:
        deterministic = self._check_work_products(
            retrieval_results=retrieval_results,
            computation_intent=computation_intent,
            operand_binding=operand_binding,
            computation_planning=computation_planning,
            computation_result=computation_result,
            retrieval_attempts=retrieval_attempts,
            computation_attempts=computation_attempts,
        )
        if deterministic is not None:
            return deterministic

        verifier = self.llm.with_structured_output(CoreVerificationResult)
        raw_result = await verifier.ainvoke(
            [
                SystemMessage(content=_VERIFICATION_PROMPT),
                HumanMessage(
                    content=json.dumps(
                        {
                            "question": question,
                            "query_understanding": understanding.model_dump(mode="json"),
                            "retrieval_results": [
                                result.model_dump(mode="json") for result in retrieval_results
                            ],
                            "computation_intent": computation_intent.model_dump(mode="json")
                            if computation_intent is not None
                            else None,
                            "computation_result": computation_result.model_dump(mode="json")
                            if computation_result is not None
                            else None,
                        },
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        assessment = (
            raw_result
            if isinstance(raw_result, CoreVerificationResult)
            else CoreVerificationResult.model_validate(raw_result)
        )
        return self._apply_retry_policy(
            assessment,
            understanding_attempts=understanding_attempts,
            retrieval_attempts=retrieval_attempts,
            computation_attempts=computation_attempts,
        )

    def _check_work_products(
        self,
        *,
        retrieval_results: tuple[RetrievalSearchResult, ...],
        computation_intent: ComputationIntent | None,
        operand_binding: OperandBindingResult | None,
        computation_planning: ComputationPlanningResult | None,
        computation_result: ComputationResult | None,
        retrieval_attempts: int,
        computation_attempts: int,
    ) -> CoreVerificationResult | None:
        missing_targets = tuple(
            result.target.need for result in retrieval_results if not result.search_results
        )
        if not retrieval_results or missing_targets:
            return self._retry_or_stop(
                retry=VerificationAction.RETRY_RETRIEVAL,
                exhausted=retrieval_attempts >= self.retry_policy.max_retrieval_attempts,
                issue=VerificationIssue(
                    code="missing_evidence",
                    reason="retrieval did not return evidence for every required target",
                    target_id=", ".join(missing_targets) if missing_targets else None,
                ),
            )

        if computation_intent is None:
            return None

        if operand_binding is None or operand_binding.missing_operand_ids:
            missing = operand_binding.missing_operand_ids if operand_binding is not None else ()
            return self._retry_or_stop(
                retry=VerificationAction.RETRY_RETRIEVAL,
                exhausted=retrieval_attempts >= self.retry_policy.max_retrieval_attempts,
                issue=VerificationIssue(
                    code="missing_computation_operand",
                    reason="retrieval evidence could not be bound to every required operand",
                    target_id=", ".join(missing) if missing else None,
                ),
            )

        if computation_planning is None:
            return self._retry_or_stop(
                retry=VerificationAction.RETRY_COMPUTATION,
                exhausted=computation_attempts >= self.retry_policy.max_computation_attempts,
                issue=VerificationIssue(
                    code="missing_computation_plan",
                    reason="no computation plan was produced",
                ),
            )

        if computation_planning.unsupported_reason is not None:
            return CoreVerificationResult(
                action=VerificationAction.CANNOT_ANSWER,
                issues=(
                    VerificationIssue(
                        code="unsupported_computation",
                        reason=computation_planning.unsupported_reason,
                    ),
                ),
            )

        if computation_result is None:
            return self._retry_or_stop(
                retry=VerificationAction.RETRY_COMPUTATION,
                exhausted=computation_attempts >= self.retry_policy.max_computation_attempts,
                issue=VerificationIssue(
                    code="missing_computation_result",
                    reason="the supported plan was not executed",
                ),
            )

        if computation_result.status == ComputationStatus.FAILURE:
            assert computation_result.error is not None
            action = (
                VerificationAction.RETRY_RETRIEVAL
                if computation_result.error.code == ComputationErrorCode.MISSING_OPERAND
                else VerificationAction.RETRY_COMPUTATION
            )
            attempts = (
                retrieval_attempts
                if action == VerificationAction.RETRY_RETRIEVAL
                else computation_attempts
            )
            limit = (
                self.retry_policy.max_retrieval_attempts
                if action == VerificationAction.RETRY_RETRIEVAL
                else self.retry_policy.max_computation_attempts
            )
            if computation_result.error.code == ComputationErrorCode.UNSUPPORTED_OPERATION:
                action = VerificationAction.CANNOT_ANSWER
            return self._retry_or_stop(
                retry=action,
                exhausted=attempts >= limit,
                issue=VerificationIssue(
                    code=computation_result.error.code,
                    reason=computation_result.error.message,
                    target_id=computation_result.error.expression_path,
                ),
            )

        return None

    def _apply_retry_policy(
        self,
        result: CoreVerificationResult,
        *,
        understanding_attempts: int,
        retrieval_attempts: int,
        computation_attempts: int,
    ) -> CoreVerificationResult:
        exhausted = {
            VerificationAction.RETRY_UNDERSTANDING: (
                understanding_attempts >= self.retry_policy.max_understanding_attempts
            ),
            VerificationAction.RETRY_RETRIEVAL: (
                retrieval_attempts >= self.retry_policy.max_retrieval_attempts
            ),
            VerificationAction.RETRY_COMPUTATION: (
                computation_attempts >= self.retry_policy.max_computation_attempts
            ),
        }
        if exhausted.get(result.action, False):
            return CoreVerificationResult(
                action=VerificationAction.CANNOT_ANSWER,
                issues=result.issues
                + (
                    VerificationIssue(
                        code="retry_exhausted",
                        reason=f"retry budget exhausted for {result.action}",
                    ),
                ),
            )
        return result

    @staticmethod
    def _retry_or_stop(
        *,
        retry: VerificationAction,
        exhausted: bool,
        issue: VerificationIssue,
    ) -> CoreVerificationResult:
        return CoreVerificationResult(
            action=VerificationAction.CANNOT_ANSWER if exhausted else retry,
            issues=(issue,),
        )


class CoreVerificationNodeInput(TypedDict):
    question: str
    query_understanding: QueryUnderstanding
    retrieval_results: list[RetrievalSearchResult]
    computation_intent: NotRequired[ComputationIntent | None]
    operand_binding: NotRequired[OperandBindingResult]
    computation_planning: NotRequired[ComputationPlanningResult]
    computation_result: NotRequired[ComputationResult]
    understanding_attempts: NotRequired[int]
    retrieval_attempts: NotRequired[int]
    computation_attempts: NotRequired[int]


class CoreVerificationNodeOutput(TypedDict):
    core_verification: CoreVerificationResult


def create_core_verification_node(
    service: CoreVerificationService,
) -> Callable[[CoreVerificationNodeInput], Awaitable[CoreVerificationNodeOutput]]:
    async def node(state: CoreVerificationNodeInput) -> CoreVerificationNodeOutput:
        result = await service.verify(
            question=state["question"],
            understanding=state["query_understanding"],
            retrieval_results=tuple(state["retrieval_results"]),
            computation_intent=state.get("computation_intent"),
            operand_binding=state.get("operand_binding"),
            computation_planning=state.get("computation_planning"),
            computation_result=state.get("computation_result"),
            understanding_attempts=state.get("understanding_attempts", 0),
            retrieval_attempts=state.get("retrieval_attempts", 0),
            computation_attempts=state.get("computation_attempts", 0),
        )
        return {"core_verification": result}

    return node

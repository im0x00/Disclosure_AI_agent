# reasoning/generate_answer/nodes.py
from collections.abc import Awaitable, Callable
from typing import NotRequired

from langgraph.types import interrupt
from typing_extensions import (
    TypedDict,
)

from reasoning.computing.models import ComputationResult, ComputationStatus
from reasoning.core.core_models import ComputationIntent, CoreVerificationResult, RuntimeFailure
from reasoning.core.evidence_adapters import evidence_reference_pairs
from reasoning.query_understanding.models import (
    QuerySafetyResult,
    QueryUnderstanding,
)
from reasoning.retrieval.models import (
    RetrievalSearchResult,
)

from .models import (
    AnswerVerificationIssue,
    AnswerVerificationResult,
    AnswerVerificationStatus,
    CannotAnswerResponse,
    FinalResponse,
    Response,
)
from .services import ResponseGenerationService


class ClarificationNodeInput(TypedDict):
    query_understanding: QueryUnderstanding
    clarification_answers: NotRequired[tuple[str, ...]]


class ClarificationNodeOutput(TypedDict):
    clarification_answers: tuple[str, ...]


class FinalResponseNodeInput(TypedDict):
    query_understanding: QueryUnderstanding

    retrieval_results: list[RetrievalSearchResult]
    computation_intent: NotRequired[ComputationIntent | None]
    computation_result: NotRequired[ComputationResult]
    answer_verification: NotRequired[AnswerVerificationResult]
    answer_generation_attempts: NotRequired[int]


class ResponseNodeOutput(TypedDict):
    response: Response


class FinalResponseNodeOutput(ResponseNodeOutput):
    answer_generation_attempts: int


class CannotAnswerNodeInput(TypedDict, total=False):
    core_verification: CoreVerificationResult
    runtime_failure: RuntimeFailure
    query_safety: QuerySafetyResult
    answer_verification: AnswerVerificationResult


class AnswerVerificationNodeInput(TypedDict):
    response: Response


class AnswerVerificationNodeOutput(TypedDict):
    answer_verification: AnswerVerificationResult


def create_clarification_node(
    service: ResponseGenerationService,
) -> Callable[
    [ClarificationNodeInput],
    Awaitable[ClarificationNodeOutput],
]:

    async def node(
        state: ClarificationNodeInput,
    ) -> ClarificationNodeOutput:

        response = await service.clarify(state["query_understanding"])

        resume_value = interrupt(response.model_dump(mode="json"))
        if isinstance(resume_value, str):
            answer = resume_value.strip()
        elif isinstance(resume_value, dict) and isinstance(resume_value.get("answer"), str):
            answer = resume_value["answer"].strip()
        else:
            raise ValueError("clarification resume must be a string or {'answer': string}")
        if not answer:
            raise ValueError("clarification answer must not be empty")
        return {
            "clarification_answers": state.get("clarification_answers", ()) + (answer,),
        }

    return node


def create_final_answer_node(
    service: ResponseGenerationService,
) -> Callable[
    [FinalResponseNodeInput],
    Awaitable[FinalResponseNodeOutput],
]:

    async def node(
        state: FinalResponseNodeInput,
    ) -> FinalResponseNodeOutput:

        computation_result = (
            state.get("computation_result") if state.get("computation_intent") is not None else None
        )
        previous_verification = state.get("answer_verification")
        feedback = previous_verification.issues if previous_verification else ()
        response = await service.answer(
            understanding=state["query_understanding"],
            retrieval_results=state["retrieval_results"],
            computation_result=computation_result,
            feedback=feedback,
        )

        return {
            "response": response,
            "answer_generation_attempts": state.get("answer_generation_attempts", 0) + 1,
        }

    return node


def create_cannot_answer_node() -> Callable[[CannotAnswerNodeInput], ResponseNodeOutput]:
    def node(state: CannotAnswerNodeInput) -> ResponseNodeOutput:
        runtime_failure = state.get("runtime_failure")
        query_safety = state.get("query_safety")
        answer_verification = state.get("answer_verification")
        core_verification = state.get("core_verification")
        if runtime_failure is not None:
            reasons = [f"{runtime_failure.node} failed after {runtime_failure.attempts} attempts"]
        elif query_safety is not None and not query_safety.is_safe:
            reasons = [query_safety.reason]
        elif answer_verification is not None and answer_verification.issues:
            reasons = [issue.reason for issue in answer_verification.issues]
        elif core_verification is not None:
            reasons = [issue.reason for issue in core_verification.issues]
        else:
            reasons = []
        response = CannotAnswerResponse(
            type="cannot_answer",
            main_text="The supplied disclosures do not support a reliable answer.",
            reasons=reasons or ["No answerable evidence path remains."],
        )
        return {"response": response}

    return node


def create_answer_verification_node() -> Callable[
    [AnswerVerificationNodeInput], AnswerVerificationNodeOutput
]:
    def node(state: AnswerVerificationNodeInput) -> AnswerVerificationNodeOutput:
        response = state["response"]
        if not isinstance(response, FinalResponse):
            return {"answer_verification": AnswerVerificationResult()}

        allowed_references = evidence_reference_pairs(response.evidences)
        issues: list[AnswerVerificationIssue] = []
        for index, claim in enumerate(response.claims):
            if not claim.evidence_refs and not claim.uses_computation:
                issues.append(
                    AnswerVerificationIssue(
                        code="ungrounded_claim",
                        reason="claim has neither an evidence citation nor a computation reference",
                        claim_index=index,
                    )
                )
            if any(
                (reference.document_id, reference.grain_id) not in allowed_references
                for reference in claim.evidence_refs
            ):
                issues.append(
                    AnswerVerificationIssue(
                        code="unknown_evidence_reference",
                        reason="claim cites evidence that was not retrieved",
                        claim_index=index,
                    )
                )
            if claim.uses_computation:
                computation = response.computation
                if computation is None or computation.status != ComputationStatus.SUCCESS:
                    issues.append(
                        AnswerVerificationIssue(
                            code="missing_computation",
                            reason="claim references a successful computation that is not present",
                            claim_index=index,
                        )
                    )
                elif claim.computed_value != computation.value:
                    issues.append(
                        AnswerVerificationIssue(
                            code="computation_value_mismatch",
                            reason=(
                                "claim value does not equal the deterministic computation result"
                            ),
                            claim_index=index,
                        )
                    )

        computation = response.computation
        if computation is not None and any(
            (reference.document_id, reference.grain_id) not in allowed_references
            for reference in computation.evidence_refs
        ):
            issues.append(
                AnswerVerificationIssue(
                    code="untraceable_computation",
                    reason="computation uses evidence that was not retrieved",
                )
            )
        return {
            "answer_verification": AnswerVerificationResult(
                status=(AnswerVerificationStatus.FAIL if issues else AnswerVerificationStatus.PASS),
                issues=tuple(issues),
            )
        }

    return node

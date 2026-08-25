from typing import NotRequired

from typing_extensions import (
    TypedDict,
)

from reasoning.computing.models import (
    ComputationPlanningResult,
    ComputationResult,
    Operand,
    OperandBindingResult,
)
from reasoning.core_models import ComputationIntent, CoreVerificationResult
from reasoning.generate_answer.models import AnswerVerificationResult, Response
from reasoning.query_understanding.models import QueryUnderstanding
from reasoning.retrieval.models import RetrievalFrame, RetrievalSearchResult


class DisclosureAIInput(TypedDict):
    question: str


class DisclosureAIOutput(TypedDict):
    response: Response


class DisclosureAIState(TypedDict):
    question: str

    query_understanding: NotRequired[QueryUnderstanding]

    computation_intent: NotRequired[ComputationIntent | None]

    retrieval_frame: NotRequired[RetrievalFrame]

    retrieval_results: NotRequired[list[RetrievalSearchResult]]

    operand_binding: NotRequired[OperandBindingResult]

    operands: NotRequired[tuple[Operand, ...]]

    computation_planning: NotRequired[ComputationPlanningResult]

    computation_result: NotRequired[ComputationResult]

    core_verification: NotRequired[CoreVerificationResult]

    response: NotRequired[Response]

    answer_verification: NotRequired[AnswerVerificationResult]

    understanding_attempts: NotRequired[int]

    retrieval_attempts: NotRequired[int]

    computation_attempts: NotRequired[int]

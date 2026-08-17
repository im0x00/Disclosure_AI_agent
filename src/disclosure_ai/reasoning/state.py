from typing import NotRequired

from typing_extensions import (
    TypedDict,
)

from disclosure_ai.reasoning.generate_response.models import Response
from disclosure_ai.reasoning.query_understanding.models import QueryUnderstanding
from disclosure_ai.reasoning.retrieval.models import RetrievalFrame, RetrievalSearchResult


class DisclosureAIInput(TypedDict):
    question: str


class DisclosureAIOutput(TypedDict):
    response: Response


class DisclosureAIState(TypedDict):
    question: str

    query_understanding: NotRequired[QueryUnderstanding]

    retrieval_frame: NotRequired[RetrievalFrame]

    retrieval_results: NotRequired[list[RetrievalSearchResult]]

    response: NotRequired[Response]

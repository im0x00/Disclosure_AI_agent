from typing import Annotated, Literal

from pydantic import BaseModel, Field

from disclosure_ai.reasoning.query_understanding.models import ContextPoint
from disclosure_ai.reasoning.retrieval.models import RetrievalSearchResult


class ClarificationResponse(BaseModel):
    type: Literal["clarification"]
    main_text: str
    missing_context_keys: list[ContextPoint]


class FinalResponse(BaseModel):
    type: Literal["final"]
    main_text: str
    evidences: list[RetrievalSearchResult]


Response = Annotated[
    ClarificationResponse | FinalResponse,
    Field(discriminator="type"),
]

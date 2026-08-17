from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from disclosure_ai.reasoning.query_understanding.models import ContextPoint, QueryUnderstanding


class EvidenceTarget(BaseModel):
    need: str
    supported_by: ContextPoint


class RetrievalFrame(BaseModel):
    query_understanding: QueryUnderstanding
    evidence_targets: list[EvidenceTarget] = Field(default_factory=list)


class RetrievedEvidence(BaseModel):
    document_id: str
    node_id: UUID
    node_type: Literal["section", "field", "block", "table_row", "cell"]
    text: str
    source_path: str
    start_byte: int = Field(ge=0)
    end_byte: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalSearchResult(BaseModel):
    target: EvidenceTarget
    search_results: list[RetrievedEvidence] = Field(default_factory=list)

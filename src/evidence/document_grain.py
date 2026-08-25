from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evidence.document_tree import SourceRange


class GrainKind(StrEnum):
    DOCUMENT = "document"
    PROSE = "prose"
    TABLE = "table"
    IMAGE = "image"


class SemanticContext(BaseModel):
    """Minimal repeated context needed to understand a grain by itself."""

    model_config = ConfigDict(frozen=True)

    heading_path: tuple[str, ...] = ()
    caption: str | None = None
    unit: str | None = None
    table_headers: tuple[str, ...] = ()
    table_position: str | None = None
    notes: tuple[str, ...] = ()


class SourceAddress(BaseModel):
    """Exact source position and structural position of a grain's core content."""

    model_config = ConfigDict(frozen=True)

    artifact_id: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    scope_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    core_ranges: tuple[SourceRange, ...] = Field(min_length=1)
    context_ranges: tuple[SourceRange, ...] = ()

    @model_validator(mode="after")
    def validate_ranges_belong_to_artifact(self) -> SourceAddress:
        for source_range in (*self.core_ranges, *self.context_ranges):
            if source_range.artifact_id != self.artifact_id:
                raise ValueError("grain source range artifact mismatch")
            if source_range.source_path != self.source_path:
                raise ValueError("grain source range path mismatch")
        return self


class DocumentGrain(BaseModel):
    """A self-readable runtime unit that remains exactly anchored in its source."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    compiler_version: Literal["1.0"] = "1.0"
    grain_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    doc_id: str = Field(min_length=1)
    kind: GrainKind
    core_text: str = Field(min_length=1)
    rendered_text: str = Field(min_length=1)
    estimated_tokens: int = Field(gt=0)
    context: SemanticContext
    source: SourceAddress

    previous_grain_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    next_grain_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_rendered_content(self) -> DocumentGrain:
        if self.core_text not in self.rendered_text:
            raise ValueError("rendered_text must contain core_text")
        return self

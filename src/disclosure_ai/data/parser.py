"""Public parsing entry points."""

from __future__ import annotations

from disclosure_ai.data.cst import build_cst
from disclosure_ai.data.models import ParsedArtifact, SourceArtifact
from disclosure_ai.data.tokenizer import tokenize


def parse_artifact(source: SourceArtifact) -> ParsedArtifact:
    tokens = tokenize(source.content, source.envelope.detected_format)
    nodes, recovery_events = build_cst(
        tokens,
        len(source.content),
        source.envelope.detected_format,
    )
    parsed = ParsedArtifact(
        source=source,
        tokens=tokens,
        nodes=nodes,
        recovery_events=recovery_events,
    )
    parsed.assert_lossless()
    return parsed

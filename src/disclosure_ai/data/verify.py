"""Corpus-wide byte and path invariants."""

from __future__ import annotations

import hashlib
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from disclosure_ai.data.catalog import CorpusCatalog
from disclosure_ai.data.parser import parse_artifact


@dataclass(frozen=True, slots=True)
class VerificationSummary:
    files: int
    bytes: int
    tokens: int
    nodes: int
    recovery_events: int
    groups: dict[str, int]
    formats: dict[str, int]


def verify_corpus(
    corpus_root: Path | str, *, include_list_sidecars: bool = True
) -> VerificationSummary:
    catalog = CorpusCatalog(corpus_root)
    file_count = 0
    byte_count = 0
    token_count = 0
    node_count = 0
    recovery_count = 0
    groups: Counter[str] = Counter()
    formats: Counter[str] = Counter()

    for artifact in catalog.iter_artifacts(include_list_sidecars=include_list_sidecars):
        envelope = artifact.envelope
        if hashlib.sha256(artifact.content).hexdigest() != envelope.sha256:
            raise AssertionError(f"hash mismatch: {envelope.relative_path}")
        if os.fsencode(envelope.relative_path) != envelope.relative_path_bytes:
            raise AssertionError(f"path byte mismatch: {envelope.relative_path}")
        if tuple(os.fsencode(part) for part in envelope.path_parts) != envelope.path_parts_bytes:
            raise AssertionError(f"path component mismatch: {envelope.relative_path}")

        parsed = parse_artifact(artifact)
        parsed.assert_lossless()
        file_count += 1
        byte_count += len(artifact.content)
        token_count += len(parsed.tokens)
        node_count += len(parsed.nodes)
        recovery_count += len(parsed.recovery_events)
        groups[envelope.doc_group or "none"] += 1
        formats[envelope.detected_format.value] += 1

    return VerificationSummary(
        files=file_count,
        bytes=byte_count,
        tokens=token_count,
        nodes=node_count,
        recovery_events=recovery_count,
        groups=dict(sorted(groups.items())),
        formats=dict(sorted(formats.items())),
    )

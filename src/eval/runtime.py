from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from html import unescape
from pathlib import Path

from pydantic import TypeAdapter

from .models import EvalCase, ReviewStatus

_CASES_ADAPTER = TypeAdapter(list[EvalCase])
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class EvidenceCheck:
    evidence_id: str
    source_path: Path
    start_byte: int
    end_byte: int
    raw_excerpt: str
    visible_text: str


@dataclass(frozen=True)
class CaseCheck:
    case: EvalCase
    evidence: tuple[EvidenceCheck, ...]


def load_cases(path: Path) -> list[EvalCase]:
    return _CASES_ADAPTER.validate_json(path.read_text(encoding="utf-8"))


def load_manifest(corpus_root: Path) -> dict[str, dict[str, object]]:
    documents: dict[str, dict[str, object]] = {}
    with (corpus_root / "manifest.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            document = json.loads(line)
            documents[str(document["doc_id"])] = document
    return documents


def validate_case(
    case: EvalCase,
    *,
    corpus_root: Path,
    manifest: dict[str, dict[str, object]],
) -> CaseCheck:
    raw_root = (corpus_root / "raw").resolve()
    checks: list[EvidenceCheck] = []

    for evidence in case.evidence:
        document = manifest.get(evidence.doc_id)
        if document is None:
            raise ValueError(f"{case.case_id}: unknown doc_id {evidence.doc_id}")

        expected_document_path = _normalized(str(document["file_path"]))
        if not _normalized(evidence.source_path).startswith(expected_document_path + "/"):
            raise ValueError(
                f"{case.case_id}/{evidence.evidence_id}: source_path is outside its document"
            )

        source_path = (corpus_root / evidence.source_path).resolve()
        if not source_path.is_relative_to(raw_root):
            raise ValueError(
                f"{case.case_id}/{evidence.evidence_id}: source_path escapes corpus/raw"
            )
        raw_bytes = source_path.read_bytes()
        actual_hash = hashlib.sha256(raw_bytes).hexdigest()
        if actual_hash != evidence.source_sha256:
            raise ValueError(f"{case.case_id}/{evidence.evidence_id}: source SHA-256 changed")
        if evidence.end_byte > len(raw_bytes):
            raise ValueError(f"{case.case_id}/{evidence.evidence_id}: byte range exceeds source")

        excerpt = raw_bytes[evidence.start_byte : evidence.end_byte].decode("utf-8")
        for required_text in evidence.must_contain:
            if required_text not in excerpt:
                raise ValueError(
                    f"{case.case_id}/{evidence.evidence_id}: "
                    f"raw range does not contain {required_text!r}"
                )
        checks.append(
            EvidenceCheck(
                evidence_id=evidence.evidence_id,
                source_path=source_path,
                start_byte=evidence.start_byte,
                end_byte=evidence.end_byte,
                raw_excerpt=excerpt,
                visible_text=_visible_text(excerpt),
            )
        )

    return CaseCheck(case=case, evidence=tuple(checks))


def validate_suite(cases_path: Path, corpus_root: Path) -> list[CaseCheck]:
    cases = load_cases(cases_path)
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("case_id values must be unique")

    manifest = load_manifest(corpus_root)
    return [validate_case(case, corpus_root=corpus_root, manifest=manifest) for case in cases]


def render_review(check: CaseCheck) -> str:
    case = check.case
    lines = [
        f"CASE {case.case_id} [{case.bucket}] [{case.review.status}]",
        f"Question: {case.question}",
        f"Logical query: {case.logical_query.model_dump_json()}",
        f"Answerability: {case.answerability}",
        f"Expected response: {case.expected_response}",
        "",
        "Gold facts:",
    ]
    if case.facts:
        for fact in case.facts:
            qualifiers = ", ".join(
                value for value in (fact.unit, fact.period, fact.scope, fact.version) if value
            )
            suffix = f" ({qualifiers})" if qualifiers else ""
            lines.append(f"- {fact.name}: {fact.value}{suffix}")
    else:
        lines.append("- none: this case expects abstention")

    lines.extend(("", "Raw evidence:"))
    for item, evidence in zip(check.evidence, case.evidence, strict=True):
        lines.extend(
            (
                f"- {item.evidence_id}",
                f"  file: {item.source_path}",
                f"  bytes: [{item.start_byte}, {item.end_byte})",
                f"  visible: {item.visible_text}",
                f"  why: {evidence.note}",
            )
        )

    lines.extend(
        (
            "",
            "Claim rubric:",
            f"- required: {list(case.claims.required)}",
            f"- optional: {list(case.claims.optional)}",
            f"- forbidden: {list(case.claims.forbidden)}",
            "",
            "Review:",
            f"- status: {case.review.status}",
            f"- reviewer: {case.review.reviewer or '-'}",
            f"- reviewed_at: {case.review.reviewed_at or '-'}",
            f"- note: {case.review.note or '-'}",
        )
    )
    return "\n".join(lines)


def suite_summary(checks: list[CaseCheck]) -> str:
    approved = sum(check.case.review.status == ReviewStatus.APPROVED for check in checks)
    return (
        f"validated={len(checks)} raw_anchors="
        f"{sum(len(check.evidence) for check in checks)} "
        f"approved={approved} draft_or_rejected={len(checks) - approved}"
    )


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _visible_text(raw_excerpt: str) -> str:
    without_tags = _TAG_RE.sub(" ", raw_excerpt)
    return _SPACE_RE.sub(" ", unescape(without_tags)).strip()

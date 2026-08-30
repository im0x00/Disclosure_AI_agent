"""Narrow retrieval output for computing, verification, and answer generation."""

from __future__ import annotations

from reasoning.retrieval.models import RetrievalSearchResult, RetrievedGrain


def evidence_reference_pairs(
    results: tuple[RetrievalSearchResult, ...] | list[RetrievalSearchResult],
) -> frozenset[tuple[str, str]]:
    return frozenset(
        (item.document_id, item.grain_id) for result in results for item in result.search_results
    )


def binding_evidence_payload(
    results: tuple[RetrievalSearchResult, ...],
) -> list[dict[str, object]]:
    return [
        {
            "operand_id": result.target.operand_id,
            "need": result.target.need,
            "evidence": [_content_item(item) for item in result.search_results],
        }
        for result in results
    ]


def verification_evidence_payload(
    results: tuple[RetrievalSearchResult, ...],
) -> list[dict[str, object]]:
    return [
        {
            "need": result.target.need,
            "supported_context": result.target.supported_by.model_dump(mode="json"),
            "operand_id": result.target.operand_id,
            "hits": [_trace_item(item) for item in result.search_results],
        }
        for result in results
    ]


def answer_evidence_payload(
    results: list[RetrievalSearchResult],
) -> list[dict[str, object]]:
    return [
        {
            "target": result.target.need,
            "items": [_content_item(item) for item in result.search_results],
        }
        for result in results
    ]


def _content_item(item: RetrievedGrain) -> dict[str, object]:
    return {
        "document_id": item.document_id,
        "grain_id": item.grain_id,
        "text": item.text,
        "kind": item.grain.kind.value,
        "context": item.grain.context.model_dump(mode="json"),
        "source": item.grain.source.model_dump(mode="json"),
        "role": item.role.value,
        "rank": item.rank,
        "relation_path": [hop.model_dump(mode="json") for hop in item.relation_path],
    }


def _trace_item(item: RetrievedGrain) -> dict[str, object]:
    payload = _content_item(item)
    payload["scores"] = item.scores.model_dump(mode="json")
    return payload

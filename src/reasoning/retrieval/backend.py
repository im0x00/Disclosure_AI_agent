"""Deterministic retrieval orchestration over pluggable storage and models.

This module owns ranking and relation traversal.  Storage implementations only
return candidates; they do not decide which evidence is acceptable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from typing import Protocol

from evidence.document_grain import DocumentGrain
from evidence.document_relation import RelationPredicate

from .errors import RetrievalConfigurationError
from .models import (
    RelationDirection,
    RelationDiscoveryMode,
    RelationHop,
    RelationTraversal,
    RetrievalScore,
    RetrievedGrain,
    RetrievedGrainRole,
    SearchBatchResult,
    SearchRequest,
)
from .retrieval import CrossEncoder, EmbeddingProvider, RetrievalQueryConfig, VectorMetric


@dataclass(frozen=True, slots=True)
class StoredCandidate:
    grain: DocumentGrain
    lexical_score: float | None = None
    vector_score: float | None = None


@dataclass(frozen=True, slots=True)
class StoredRelation:
    relation_id: str
    source_doc_id: str
    source_grain_ids: tuple[str, ...]
    predicate: str
    target_doc_id: str
    target_grain_ids: tuple[str, ...]


class RetrievalStore(Protocol):
    async def lexical_candidates(
        self,
        request: SearchRequest,
        *,
        document_ids: tuple[str, ...] = (),
    ) -> Sequence[StoredCandidate]: ...

    async def vector_candidates(
        self,
        request: SearchRequest,
        query_embedding: Sequence[float],
        *,
        model_id: str,
        dimensions: int,
        vector_metric: VectorMetric,
        document_ids: tuple[str, ...] = (),
    ) -> Sequence[StoredCandidate]: ...

    async def count_document_grains(self, document_id: str) -> int: ...

    async def load_document_grains(self, document_id: str) -> Sequence[DocumentGrain]: ...

    async def load_grains(self, grain_ids: tuple[str, ...]) -> Sequence[DocumentGrain]: ...

    async def relations(
        self,
        document_ids: tuple[str, ...],
        *,
        predicate: str,
        direction: RelationDirection,
        as_of: date,
    ) -> Sequence[StoredRelation]: ...

    async def discover_grain_relations(
        self,
        grain_ids: tuple[str, ...],
        *,
        as_of: date,
    ) -> Sequence[StoredRelation]: ...


@dataclass(frozen=True, slots=True)
class _RankedCandidate:
    grain: DocumentGrain
    lexical_score: float | None = None
    vector_score: float | None = None
    rrf_score: float | None = None
    cross_encoder_score: float | None = None
    role: RetrievedGrainRole = RetrievedGrainRole.PRIMARY
    relation_path: tuple[RelationHop, ...] = ()


class HybridRetrievalBackend:
    """Hybrid retrieval with deterministic RRF, reranking, and edge expansion."""

    def __init__(
        self,
        *,
        store: RetrievalStore,
        embedding_provider: EmbeddingProvider,
        cross_encoder: CrossEncoder,
        config: RetrievalQueryConfig,
    ) -> None:
        self._store = store
        self._embedding_provider = embedding_provider
        self._cross_encoder = cross_encoder
        self._config = config

    async def search_many(
        self, requests: tuple[SearchRequest, ...]
    ) -> tuple[SearchBatchResult, ...]:
        if not requests:
            return ()

        embeddings = await self._embedding_provider.embed_queries(
            tuple(request.semantic_query for request in requests)
        )
        if len(embeddings) != len(requests):
            raise RetrievalConfigurationError("embedding provider returned an invalid batch size")

        results: list[SearchBatchResult] = []
        for request, embedding in zip(requests, embeddings, strict=True):
            if len(embedding) != self._embedding_provider.dimensions:
                raise RetrievalConfigurationError(
                    "embedding provider returned an invalid dimension"
                )
            hits = await self._search_one(request, embedding)
            results.append(SearchBatchResult(request=request, hits=hits))
        return tuple(results)

    async def _search_one(
        self, request: SearchRequest, embedding: Sequence[float]
    ) -> tuple[RetrievedGrain, ...]:
        primary = await self._hybrid_candidates(request, embedding)
        primary = await self._rerank(request.semantic_query, primary)
        accepted_primary = self._accepted(primary, request.minimum_score)

        expanded: list[_RankedCandidate] = []
        seed_document_ids = tuple(
            dict.fromkeys(candidate.grain.doc_id for candidate in accepted_primary)
        )
        for traversal in request.traversals:
            expanded.extend(
                await self._expand_relations(
                    request=request,
                    query_embedding=embedding,
                    semantic_query=request.semantic_query,
                    seed_document_ids=seed_document_ids,
                    traversal=traversal,
                )
            )

        expanded.extend(
            await self._discover_automatic_relations(
                request=request,
                query_embedding=embedding,
                semantic_query=request.semantic_query,
                primary_candidates=accepted_primary,
            )
        )

        merged = self._merge(primary + expanded)
        accepted = self._accepted(merged, request.minimum_score)
        accepted.sort(
            key=lambda candidate: (
                candidate.cross_encoder_score
                if candidate.cross_encoder_score is not None
                else float("-inf"),
                candidate.rrf_score if candidate.rrf_score is not None else float("-inf"),
                candidate.grain.grain_id,
            ),
            reverse=True,
        )
        return tuple(
            self._to_result(item, target_id=request.target_id, rank=rank)
            for rank, item in enumerate(accepted[: request.max_top_k], start=1)
        )

    async def _hybrid_candidates(
        self,
        request: SearchRequest,
        query_embedding: Sequence[float],
        *,
        document_ids: tuple[str, ...] = (),
    ) -> list[_RankedCandidate]:
        lexical = await self._store.lexical_candidates(request, document_ids=document_ids)
        vector = await self._store.vector_candidates(
            request,
            query_embedding,
            model_id=self._embedding_provider.model_id,
            dimensions=self._embedding_provider.dimensions,
            vector_metric=self._config.vector_metric,
            document_ids=document_ids,
        )
        return self._rrf(lexical, vector)

    def _rrf(
        self,
        lexical: Sequence[StoredCandidate],
        vector: Sequence[StoredCandidate],
    ) -> list[_RankedCandidate]:
        by_id: dict[str, _RankedCandidate] = {}
        for rank, candidate in enumerate(lexical, start=1):
            current = by_id.get(candidate.grain.grain_id)
            score = 1.0 / (self._config.rrf_k + rank)
            by_id[candidate.grain.grain_id] = _RankedCandidate(
                grain=candidate.grain,
                lexical_score=candidate.lexical_score,
                vector_score=current.vector_score if current else None,
                rrf_score=(current.rrf_score if current and current.rrf_score else 0.0) + score,
            )
        for rank, candidate in enumerate(vector, start=1):
            current = by_id.get(candidate.grain.grain_id)
            score = 1.0 / (self._config.rrf_k + rank)
            by_id[candidate.grain.grain_id] = _RankedCandidate(
                grain=candidate.grain,
                lexical_score=current.lexical_score if current else None,
                vector_score=candidate.vector_score,
                rrf_score=(current.rrf_score if current and current.rrf_score else 0.0) + score,
            )
        return sorted(
            by_id.values(),
            key=lambda candidate: (
                candidate.rrf_score or 0.0,
                candidate.grain.grain_id,
            ),
            reverse=True,
        )

    async def _rerank(
        self, query: str, candidates: Sequence[_RankedCandidate]
    ) -> list[_RankedCandidate]:
        if not candidates:
            return []
        scores = await self._cross_encoder.score(
            tuple((query, candidate.grain.rendered_text) for candidate in candidates)
        )
        if len(scores) != len(candidates):
            raise RetrievalConfigurationError("cross encoder returned an invalid batch size")
        return [
            replace(candidate, cross_encoder_score=float(score))
            for candidate, score in zip(candidates, scores, strict=True)
        ]

    async def _expand_relations(
        self,
        *,
        request: SearchRequest,
        query_embedding: Sequence[float],
        semantic_query: str,
        seed_document_ids: tuple[str, ...],
        traversal: RelationTraversal,
    ) -> list[_RankedCandidate]:
        if not seed_document_ids:
            return []

        frontier: list[tuple[str, tuple[RelationHop, ...]]] = [
            (document_id, ()) for document_id in seed_document_ids
        ]
        visited_documents = set(seed_document_ids)
        expanded: list[_RankedCandidate] = []
        depth = 0

        while frontier:
            depth += 1
            frontier_ids = tuple(document_id for document_id, _ in frontier)
            paths = {document_id: path for document_id, path in frontier}
            relations = await self._store.relations(
                frontier_ids,
                predicate=(
                    traversal.predicate.value
                    if hasattr(traversal.predicate, "value")
                    else str(traversal.predicate)
                ),
                direction=traversal.direction,
                as_of=request.as_of,
            )
            next_frontier: list[tuple[str, tuple[RelationHop, ...]]] = []

            for relation in relations:
                for origin_id in frontier_ids:
                    endpoint = self._other_endpoint(relation, origin_id)
                    if endpoint is None:
                        continue
                    destination_id, destination_grain_ids, hop_direction = endpoint
                    hop = RelationHop(
                        discovery_mode=RelationDiscoveryMode.EXPLICIT,
                        relation_id=relation.relation_id,
                        predicate=RelationPredicate(relation.predicate),
                        direction=hop_direction,
                        source_doc_id=relation.source_doc_id,
                        target_doc_id=relation.target_doc_id,
                    )
                    path = paths[origin_id] + (hop,)
                    candidates = await self._relation_candidates(
                        request=request,
                        query_embedding=query_embedding,
                        destination_id=destination_id,
                        destination_grain_ids=destination_grain_ids,
                    )
                    reranked = await self._rerank(semantic_query, candidates)
                    expanded.extend(
                        replace(
                            candidate,
                            role=RetrievedGrainRole.RELATED,
                            relation_path=path,
                        )
                        for candidate in reranked
                    )

                    if (
                        traversal.max_hops is None or depth < traversal.max_hops
                    ) and destination_id not in visited_documents:
                        visited_documents.add(destination_id)
                        next_frontier.append((destination_id, path))

            if traversal.max_hops is not None and depth >= traversal.max_hops:
                break
            frontier = next_frontier

        return expanded

    async def _discover_automatic_relations(
        self,
        *,
        request: SearchRequest,
        query_embedding: Sequence[float],
        semantic_query: str,
        primary_candidates: Sequence[_RankedCandidate],
    ) -> list[_RankedCandidate]:
        """Expand only edges directly attached to accepted primary grains."""
        if not primary_candidates:
            return []

        primary_by_grain_id = {
            candidate.grain.grain_id: candidate for candidate in primary_candidates
        }
        relations = await self._store.discover_grain_relations(
            tuple(primary_by_grain_id),
            as_of=request.as_of,
        )
        expanded: list[_RankedCandidate] = []

        for relation in relations:
            predicate = relation.predicate.lower()
            for grain_id, primary in primary_by_grain_id.items():
                endpoint = self._automatic_endpoint(
                    relation=relation,
                    predicate=predicate,
                    grain_id=grain_id,
                    origin_document_id=primary.grain.doc_id,
                )
                if endpoint is None:
                    continue

                destination_id, destination_grain_ids, direction = endpoint
                hop = RelationHop(
                    discovery_mode=RelationDiscoveryMode.AUTOMATIC,
                    relation_id=relation.relation_id,
                    predicate=RelationPredicate(relation.predicate),
                    direction=direction,
                    source_doc_id=relation.source_doc_id,
                    target_doc_id=relation.target_doc_id,
                )
                candidates = await self._relation_candidates(
                    request=request,
                    query_embedding=query_embedding,
                    destination_id=destination_id,
                    destination_grain_ids=destination_grain_ids,
                )
                reranked = await self._rerank(semantic_query, candidates)
                expanded.extend(
                    replace(
                        candidate,
                        role=RetrievedGrainRole.RELATED,
                        relation_path=(hop,),
                    )
                    for candidate in reranked
                )

        return expanded

    @staticmethod
    def _automatic_endpoint(
        *,
        relation: StoredRelation,
        predicate: str,
        grain_id: str,
        origin_document_id: str,
    ) -> tuple[str, tuple[str, ...], RelationDirection] | None:
        source_match = (
            relation.source_doc_id == origin_document_id and grain_id in relation.source_grain_ids
        )
        target_match = (
            relation.target_doc_id == origin_document_id and grain_id in relation.target_grain_ids
        )

        if predicate == "references":
            if not source_match:
                return None
            return (
                relation.target_doc_id,
                relation.target_grain_ids,
                RelationDirection.OUTGOING,
            )

        if predicate not in {"revises", "terminates"}:
            return None
        if source_match:
            return (
                relation.target_doc_id,
                relation.target_grain_ids,
                RelationDirection.OUTGOING,
            )
        if target_match:
            return (
                relation.source_doc_id,
                relation.source_grain_ids,
                RelationDirection.INCOMING,
            )
        return None

    @staticmethod
    def _other_endpoint(
        relation: StoredRelation, origin_id: str
    ) -> tuple[str, tuple[str, ...], RelationDirection] | None:
        if relation.source_doc_id == origin_id:
            return (
                relation.target_doc_id,
                relation.target_grain_ids,
                RelationDirection.OUTGOING,
            )
        if relation.target_doc_id == origin_id:
            return (
                relation.source_doc_id,
                relation.source_grain_ids,
                RelationDirection.INCOMING,
            )
        return None

    async def _relation_candidates(
        self,
        *,
        request: SearchRequest,
        query_embedding: Sequence[float],
        destination_id: str,
        destination_grain_ids: tuple[str, ...],
    ) -> list[_RankedCandidate]:
        if destination_grain_ids:
            grains = await self._store.load_grains(destination_grain_ids)
            return [_RankedCandidate(grain=grain) for grain in grains]

        count = await self._store.count_document_grains(destination_id)
        if count <= self._config.exhaustive_grain_limit:
            grains = await self._store.load_document_grains(destination_id)
            return [_RankedCandidate(grain=grain) for grain in grains]

        return await self._hybrid_candidates(
            request,
            query_embedding,
            document_ids=(destination_id,),
        )

    @staticmethod
    def _accepted(
        candidates: Sequence[_RankedCandidate], minimum_score: float
    ) -> list[_RankedCandidate]:
        return [
            candidate
            for candidate in candidates
            if candidate.cross_encoder_score is not None
            and candidate.cross_encoder_score >= minimum_score
        ]

    @staticmethod
    def _merge(candidates: Sequence[_RankedCandidate]) -> list[_RankedCandidate]:
        by_id: dict[str, _RankedCandidate] = {}
        for candidate in candidates:
            current = by_id.get(candidate.grain.grain_id)
            if current is None:
                by_id[candidate.grain.grain_id] = candidate
                continue
            current_score = (
                current.cross_encoder_score
                if current.cross_encoder_score is not None
                else float("-inf")
            )
            candidate_score = (
                candidate.cross_encoder_score
                if candidate.cross_encoder_score is not None
                else float("-inf")
            )
            if current.role is RetrievedGrainRole.PRIMARY:
                continue
            if candidate.role is RetrievedGrainRole.PRIMARY or candidate_score > current_score:
                by_id[candidate.grain.grain_id] = candidate
            elif candidate_score == current_score and len(candidate.relation_path) < len(
                current.relation_path
            ):
                by_id[candidate.grain.grain_id] = candidate
        return list(by_id.values())

    @staticmethod
    def _to_result(
        candidate: _RankedCandidate,
        *,
        target_id: str,
        rank: int,
    ) -> RetrievedGrain:
        if candidate.cross_encoder_score is None:
            raise RetrievalConfigurationError("accepted candidate is missing a cross-encoder score")
        return RetrievedGrain(
            target_id=target_id,
            grain=candidate.grain,
            role=candidate.role,
            rank=rank,
            scores=RetrievalScore(
                lexical=candidate.lexical_score,
                vector=candidate.vector_score,
                rrf=candidate.rrf_score,
                cross_encoder=candidate.cross_encoder_score,
            ),
            relation_path=candidate.relation_path,
        )

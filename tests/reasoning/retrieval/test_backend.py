from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pytest

from evidence.document_grain import (
    DocumentGrain,
    GrainKind,
    SemanticContext,
    SourceAddress,
)
from reasoning.query_understanding.models import ContextPoint, ContextStatus
from reasoning.retrieval.backend import (
    HybridRetrievalBackend,
    StoredCandidate,
    StoredRelation,
)
from reasoning.retrieval.models import (
    EvidenceTarget,
    RelationDirection,
    RelationDiscoveryMode,
    RelationTraversal,
    RetrievedGrainRole,
    SearchFilters,
    SearchRequest,
    VersionPolicy,
)
from reasoning.retrieval.retrieval import RetrievalQueryConfig, VectorMetric


def _target() -> EvidenceTarget:
    return EvidenceTarget(
        need="query",
        supported_by=ContextPoint(key="query", status=ContextStatus.KNOWN, value="query"),
    )


def _grain(grain_id: str, doc_id: str, text: str) -> DocumentGrain:
    return DocumentGrain.model_construct(
        schema_version="1.0",
        compiler_version="1.0",
        grain_id=grain_id,
        doc_id=doc_id,
        kind=GrainKind.PROSE,
        core_text=text,
        rendered_text=text,
        estimated_tokens=1,
        context=SemanticContext(),
        source=SourceAddress.model_construct(
            artifact_id="test-artifact",
            source_path="test.xml",
            ordinal=0,
            scope_id="0" * 64,
            core_ranges=(),
            context_ranges=(),
        ),
        previous_grain_id=None,
        next_grain_id=None,
    )


class _EmbeddingProvider:
    model_id = "test-embedding"
    dimensions = 2

    async def embed_queries(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple((1.0, 0.0) for _ in texts)

    async def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple((1.0, 0.0) for _ in texts)


class _CrossEncoder:
    async def score(self, pairs: tuple[tuple[str, str], ...]) -> tuple[float, ...]:
        values = {"primary": 0.8, "related-high": 0.9, "related-low": 0.7}
        return tuple(values[text] for _, text in pairs)


class _Store:
    def __init__(self) -> None:
        self.exhaustive_loads: list[str] = []
        self.automatic_relations: tuple[StoredRelation, ...] = ()
        self.primary = _grain("1" * 64, "doc-new", "primary")
        self.related_high = _grain("2" * 64, "doc-old", "related-high")
        self.related_low = _grain("3" * 64, "doc-old", "related-low")

    async def lexical_candidates(
        self,
        request: SearchRequest,
        *,
        document_ids: tuple[str, ...] = (),
    ) -> Sequence[StoredCandidate]:
        if document_ids:
            return ()
        return (StoredCandidate(self.primary, lexical_score=1.0),)

    async def vector_candidates(
        self,
        request: SearchRequest,
        query_embedding: Sequence[float],
        *,
        model_id: str,
        dimensions: int,
        vector_metric: VectorMetric,
        document_ids: tuple[str, ...] = (),
    ) -> Sequence[StoredCandidate]:
        return ()

    async def count_document_grains(self, document_id: str) -> int:
        return 2

    async def load_document_grains(self, document_id: str) -> Sequence[DocumentGrain]:
        self.exhaustive_loads.append(document_id)
        return (self.related_high, self.related_low)

    async def load_grains(self, grain_ids: tuple[str, ...]) -> Sequence[DocumentGrain]:
        by_id = {
            self.related_high.grain_id: self.related_high,
            self.related_low.grain_id: self.related_low,
        }
        return tuple(by_id[grain_id] for grain_id in grain_ids if grain_id in by_id)

    async def relations(
        self,
        document_ids: tuple[str, ...],
        *,
        predicate: str,
        direction: RelationDirection,
        as_of: date,
    ) -> Sequence[StoredRelation]:
        if "doc-new" not in document_ids:
            return ()
        return (
            StoredRelation(
                relation_id="4" * 64,
                source_doc_id="doc-new",
                source_grain_ids=(),
                predicate="revises",
                target_doc_id="doc-old",
                target_grain_ids=(),
            ),
        )

    async def discover_grain_relations(
        self,
        grain_ids: tuple[str, ...],
        *,
        as_of: date,
    ) -> Sequence[StoredRelation]:
        return self.automatic_relations


@pytest.mark.asyncio
async def test_relation_expansion_is_reranked_and_globally_limited() -> None:
    store = _Store()
    backend = HybridRetrievalBackend(
        store=store,
        embedding_provider=_EmbeddingProvider(),
        cross_encoder=_CrossEncoder(),
        config=RetrievalQueryConfig(
            lexical_candidate_k=10,
            vector_candidate_k=10,
            max_top_k=2,
            minimum_score=0.5,
            exhaustive_grain_limit=10,
        ),
    )
    request = SearchRequest.model_construct(
        target_id="request-1",
        target=_target(),
        semantic_query="query",
        lexical_terms=("query",),
        filters=SearchFilters(),
        version_policy=VersionPolicy.ALL_VERSIONS,
        as_of=date(2025, 1, 1),
        traversals=(
            RelationTraversal(
                predicate="revises",
                direction=RelationDirection.BOTH,
                max_hops=None,
            ),
        ),
        lexical_candidate_k=10,
        vector_candidate_k=10,
        max_top_k=2,
        minimum_score=0.5,
    )

    batch = await backend.search_many((request,))

    assert store.exhaustive_loads == ["doc-old"]
    assert [hit.grain.grain_id for hit in batch[0].hits] == ["2" * 64, "1" * 64]
    assert batch[0].hits[0].role is RetrievedGrainRole.RELATED
    assert len(batch[0].hits[0].relation_path) == 1
    assert batch[0].hits[0].scores.cross_encoder == 0.9


@pytest.mark.asyncio
async def test_grain_scoped_edge_is_discovered_without_explicit_traversal() -> None:
    store = _Store()
    store.automatic_relations = (
        StoredRelation(
            relation_id="5" * 64,
            source_doc_id="doc-new",
            source_grain_ids=("1" * 64,),
            predicate="references",
            target_doc_id="doc-old",
            target_grain_ids=("2" * 64,),
        ),
    )
    backend = HybridRetrievalBackend(
        store=store,
        embedding_provider=_EmbeddingProvider(),
        cross_encoder=_CrossEncoder(),
        config=RetrievalQueryConfig(
            lexical_candidate_k=10,
            vector_candidate_k=10,
            max_top_k=2,
            minimum_score=0.5,
            exhaustive_grain_limit=10,
        ),
    )
    request = SearchRequest.model_construct(
        target_id="request-automatic",
        target=_target(),
        semantic_query="query",
        lexical_terms=("query",),
        filters=SearchFilters(),
        version_policy=VersionPolicy.ALL_VERSIONS,
        as_of=date(2025, 1, 1),
        traversals=(),
        lexical_candidate_k=10,
        vector_candidate_k=10,
        max_top_k=2,
        minimum_score=0.5,
    )

    batch = await backend.search_many((request,))

    related = next(hit for hit in batch[0].hits if hit.grain.grain_id == "2" * 64)
    assert related.relation_path[0].discovery_mode is RelationDiscoveryMode.AUTOMATIC

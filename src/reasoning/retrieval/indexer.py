"""Incremental document-grain embedding indexer.

Calling code owns scheduling and transactions; this module only batches model
work and idempotent database upserts.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
from time import monotonic
from typing import Any, cast

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .retrieval import EmbeddingProvider


@dataclass(frozen=True, slots=True)
class EmbeddingIndexReport:
    indexed: int
    model_id: str
    dimensions: int


@dataclass(frozen=True, slots=True)
class EmbeddingIndexProgress:
    indexed: int
    total: int
    elapsed_seconds: float

    @property
    def grains_per_second(self) -> float:
        if self.elapsed_seconds <= 0:
            return 0.0
        return self.indexed / self.elapsed_seconds

    @property
    def eta_seconds(self) -> float | None:
        rate = self.grains_per_second
        if rate <= 0:
            return None
        return max(0, self.total - self.indexed) / rate


class DocumentGrainEmbeddingIndexer:
    def __init__(
        self,
        *,
        pool: AsyncConnectionPool[Any],
        embedding_provider: EmbeddingProvider,
        batch_size: int,
        scheduling_window_batches: int,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if scheduling_window_batches <= 0:
            raise ValueError("scheduling_window_batches must be positive")
        self._pool = pool
        self._embedding_provider = embedding_provider
        self._batch_size = batch_size
        self._scheduling_window_size = batch_size * scheduling_window_batches

    async def index_pending(
        self,
        *,
        max_grains: int | None = None,
        document_ids: Collection[str] | None = None,
        progress: Callable[[EmbeddingIndexProgress], None] | None = None,
        progress_every_windows: int = 1,
    ) -> EmbeddingIndexReport:
        if progress_every_windows < 1:
            raise ValueError("progress_every_windows must be positive")
        scoped_document_ids = None if document_ids is None else tuple(sorted(set(document_ids)))
        pending = await self._count_pending(scoped_document_ids)
        total = pending if max_grains is None else min(pending, max_grains)
        started_at = monotonic()
        indexed = 0
        completed_windows = 0
        if progress is not None:
            progress(
                EmbeddingIndexProgress(
                    indexed=0,
                    total=total,
                    elapsed_seconds=0.0,
                )
            )
        while max_grains is None or indexed < max_grains:
            current_limit = self._scheduling_window_size
            if max_grains is not None:
                current_limit = min(current_limit, max_grains - indexed)
            rows = await self._load_pending(current_limit, scoped_document_ids)
            if not rows:
                break

            rows.sort(key=_embedding_schedule_key)
            texts = tuple(str(row["rendered_text"]) for row in rows)
            embeddings = await self._embedding_provider.embed_documents(texts)
            if len(embeddings) != len(rows):
                raise ValueError("embedding provider returned an invalid batch size")
            await self._upsert(rows, embeddings)
            indexed += len(rows)
            completed_windows += 1
            if progress is not None and (
                completed_windows % progress_every_windows == 0 or indexed >= total
            ):
                progress(
                    EmbeddingIndexProgress(
                        indexed=indexed,
                        total=total,
                        elapsed_seconds=monotonic() - started_at,
                    )
                )

        return EmbeddingIndexReport(
            indexed=indexed,
            model_id=self._embedding_provider.model_id,
            dimensions=self._embedding_provider.dimensions,
        )

    async def _count_pending(self, document_ids: tuple[str, ...] | None) -> int:
        if document_ids == ():
            return 0
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT count(*)
                      FROM corpus.document_grain AS g
                      LEFT JOIN corpus.document_grain_embedding AS e
                        ON e.grain_id = g.grain_id
                       AND e.model_id = %(model_id)s
                       AND e.dimensions = %(dimensions)s
                     WHERE e.grain_id IS NULL
                       AND (%(all_documents)s OR g.doc_id = ANY(%(document_ids)s::text[]))
                    """,
                    {
                        "model_id": self._embedding_provider.model_id,
                        "dimensions": self._embedding_provider.dimensions,
                        "all_documents": document_ids is None,
                        "document_ids": list(document_ids or ()),
                    },
                )
                row = await cursor.fetchone()
                if row is None:
                    raise RuntimeError("pending embedding count returned no row")
                return int(row[0])

    async def _load_pending(
        self,
        limit: int,
        document_ids: tuple[str, ...] | None,
    ) -> list[dict[str, object]]:
        if document_ids == ():
            return []
        async with self._pool.connection() as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    """
                    SELECT g.grain_id, g.rendered_text, g.estimated_tokens
                      FROM corpus.document_grain AS g
                      LEFT JOIN corpus.document_grain_embedding AS e
                        ON e.grain_id = g.grain_id
                       AND e.model_id = %(model_id)s
                       AND e.dimensions = %(dimensions)s
                     WHERE e.grain_id IS NULL
                       AND (%(all_documents)s OR g.doc_id = ANY(%(document_ids)s::text[]))
                     ORDER BY g.grain_id ASC
                     LIMIT %(batch_size)s
                    """,
                    {
                        "model_id": self._embedding_provider.model_id,
                        "dimensions": self._embedding_provider.dimensions,
                        "batch_size": limit,
                        "all_documents": document_ids is None,
                        "document_ids": list(document_ids or ()),
                    },
                )
                return cast(list[dict[str, object]], await cursor.fetchall())

    async def _upsert(
        self,
        rows: list[dict[str, object]],
        embeddings: tuple[tuple[float, ...], ...],
    ) -> None:
        parameters: list[dict[str, object]] = []
        for row, embedding in zip(rows, embeddings, strict=True):
            if len(embedding) != self._embedding_provider.dimensions:
                raise ValueError("embedding provider returned an invalid dimension")
            parameters.append(
                {
                    "grain_id": row["grain_id"],
                    "model_id": self._embedding_provider.model_id,
                    "dimensions": self._embedding_provider.dimensions,
                    "embedding": "[" + ",".join(str(float(value)) for value in embedding) + "]",
                }
            )

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.executemany(
                    """
                    INSERT INTO corpus.document_grain_embedding (
                        grain_id, model_id, dimensions, embedding, embedded_at
                    ) VALUES (
                        %(grain_id)s,
                        %(model_id)s,
                        %(dimensions)s,
                        %(embedding)s::vector,
                        now()
                    )
                    ON CONFLICT (grain_id, model_id) DO UPDATE
                    SET dimensions = EXCLUDED.dimensions,
                        embedding = EXCLUDED.embedding,
                        embedded_at = EXCLUDED.embedded_at
                    """,
                    parameters,
                )
            await connection.commit()


def _embedding_schedule_key(row: dict[str, object]) -> tuple[int, str]:
    estimated_tokens = row["estimated_tokens"]
    if not isinstance(estimated_tokens, int):
        raise TypeError("estimated_tokens must be an integer")
    return estimated_tokens, str(row["grain_id"])

"""PostgreSQL implementation backed by pg_trgm and pgvector.

The corpus owns document metadata, so metadata/version selection is injected as
``DocumentScopeResolver`` instead of being duplicated in retrieval SQL.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Protocol, cast

from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from evidence.document_grain import DocumentGrain

from .backend import RetrievalStore, StoredCandidate, StoredRelation
from .errors import RetrievalDataError
from .models import RelationDirection, SearchRequest, VersionPolicy
from .retrieval import VectorMetric


class DocumentScopeResolver(Protocol):
    """Resolve hard document filters against the corpus metadata catalog."""

    async def resolve(self, request: SearchRequest) -> tuple[str, ...]: ...

    async def filter_as_of(
        self, document_ids: tuple[str, ...], *, as_of: date
    ) -> tuple[str, ...]: ...


class PostgresDocumentScopeResolver:
    """Resolve only compiler-approved hard filters against canonical corpus rows."""

    def __init__(self, pool: AsyncConnectionPool[Any]) -> None:
        self._pool = pool

    async def resolve(self, request: SearchRequest) -> tuple[str, ...]:
        filters = request.filters
        clauses: list[sql.Composable] = [sql.SQL("d.receipt_date <= %(as_of)s")]
        parameters: dict[str, object] = {"as_of": request.as_of}

        if filters.corp_codes:
            clauses.append(sql.SQL("d.corp_code = ANY(%(corp_codes)s)"))
            parameters["corp_codes"] = list(filters.corp_codes)
        if filters.company_names:
            clauses.append(
                sql.SQL(
                    """
                    (lower(c.corp_name) = ANY(%(company_names)s)
                     OR lower(c.listed_name) = ANY(%(company_names)s)
                     OR lower(coalesce(c.corp_eng_name, '')) = ANY(%(company_names)s))
                    """
                )
            )
            parameters["company_names"] = [value.casefold() for value in filters.company_names]
        if filters.doc_groups:
            clauses.append(sql.SQL("d.doc_group = ANY(%(doc_groups)s)"))
            parameters["doc_groups"] = list(filters.doc_groups)
        if filters.date_from is not None:
            clauses.append(sql.SQL("d.receipt_date >= %(date_from)s"))
            parameters["date_from"] = filters.date_from
        if filters.date_to is not None:
            clauses.append(sql.SQL("d.receipt_date <= %(date_to)s"))
            parameters["date_to"] = filters.date_to
        if filters.base_year is not None:
            clauses.append(sql.SQL("d.base_year = %(base_year)s"))
            parameters["base_year"] = filters.base_year
        if filters.base_month is not None:
            clauses.append(sql.SQL("d.base_month = %(base_month)s"))
            parameters["base_month"] = filters.base_month
        if filters.exact_doc_ids:
            clauses.append(sql.SQL("d.doc_id = ANY(%(exact_doc_ids)s)"))
            parameters["exact_doc_ids"] = list(filters.exact_doc_ids)
        if request.version_policy == VersionPolicy.LATEST_AS_OF:
            clauses.append(
                sql.SQL(
                    """
                    NOT EXISTS (
                        SELECT 1
                          FROM corpus.document_relation AS revision
                          JOIN corpus.disclosure_document AS newer
                            ON newer.doc_id = revision.source_doc_id
                         WHERE revision.predicate = 'revises'
                           AND revision.target_doc_id = d.doc_id
                           AND newer.receipt_date <= %(as_of)s
                    )
                    """
                )
            )

        rows = await self._fetch_all(
            sql.SQL(
                """
                SELECT d.doc_id
                  FROM corpus.disclosure_document AS d
                  JOIN corpus.company AS c ON c.corp_code = d.corp_code
                 WHERE {where_clause}
                 ORDER BY d.receipt_date DESC, d.receipt_no DESC
                """
            ).format(where_clause=sql.SQL(" AND ").join(clauses)),
            parameters,
        )
        return tuple(str(row["doc_id"]) for row in rows)

    async def filter_as_of(
        self,
        document_ids: tuple[str, ...],
        *,
        as_of: date,
    ) -> tuple[str, ...]:
        if not document_ids:
            return ()
        rows = await self._fetch_all(
            sql.SQL(
                """
                SELECT doc_id
                  FROM corpus.disclosure_document
                 WHERE doc_id = ANY(%(document_ids)s)
                   AND receipt_date <= %(as_of)s
                 ORDER BY receipt_date DESC, receipt_no DESC
                """
            ),
            {"document_ids": list(document_ids), "as_of": as_of},
        )
        return tuple(str(row["doc_id"]) for row in rows)

    async def _fetch_all(
        self,
        statement: sql.Composable,
        parameters: Mapping[str, object],
    ) -> list[dict[str, object]]:
        async with self._pool.connection() as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(statement, parameters)
                return cast(list[dict[str, object]], await cursor.fetchall())


class PostgresRetrievalStore(RetrievalStore):
    def __init__(
        self,
        *,
        pool: AsyncConnectionPool[Any],
        scope_resolver: DocumentScopeResolver,
    ) -> None:
        self._pool = pool
        self._scope_resolver = scope_resolver

    async def lexical_candidates(
        self,
        request: SearchRequest,
        *,
        document_ids: tuple[str, ...] = (),
    ) -> Sequence[StoredCandidate]:
        scoped_ids = await self._scope(request, document_ids)
        if not scoped_ids:
            return ()
        query = " ".join(request.lexical_terms) or request.semantic_query
        statement = sql.SQL(
            """
            SELECT to_jsonb(g) AS grain,
                   GREATEST(
                       similarity(g.rendered_text, %(query)s),
                       word_similarity(%(query)s, g.rendered_text),
                       ts_rank_cd(
                           to_tsvector('simple', g.rendered_text),
                           plainto_tsquery('simple', %(query)s)
                       )
                   ) AS lexical_score
              FROM corpus.document_grain AS g
             WHERE g.doc_id = ANY(%(document_ids)s)
             ORDER BY lexical_score DESC, g.grain_id ASC
             LIMIT %(candidate_k)s
            """
        )
        rows = await self._fetch_all(
            statement,
            {
                "query": query,
                "document_ids": list(scoped_ids),
                "candidate_k": request.lexical_candidate_k,
            },
        )
        return tuple(
            StoredCandidate(
                grain=_document_grain(row["grain"]),
                lexical_score=_float_value(row["lexical_score"], field="lexical_score"),
            )
            for row in rows
        )

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
        scoped_ids = await self._scope(request, document_ids)
        if not scoped_ids:
            return ()
        vector_text = "[" + ",".join(str(float(value)) for value in query_embedding) + "]"
        operator, score_prefix = _vector_sql(vector_metric)
        distance = sql.SQL(
            "(e.embedding::vector({dimensions})) {operator} (%(embedding)s::vector({dimensions}))"
        ).format(
            dimensions=sql.Literal(dimensions),
            operator=sql.SQL(operator),
        )
        statement = sql.SQL(
            """
            SELECT to_jsonb(g) AS grain,
                   {score_prefix}({distance}) AS vector_score
              FROM corpus.document_grain AS g
              JOIN corpus.document_grain_embedding AS e
                ON e.grain_id = g.grain_id
             WHERE g.doc_id = ANY(%(document_ids)s)
               AND e.model_id = %(model_id)s
               AND e.dimensions = %(dimensions)s
             ORDER BY {distance} ASC, g.grain_id ASC
             LIMIT %(candidate_k)s
            """
        ).format(
            score_prefix=sql.SQL(score_prefix),
            distance=distance,
        )
        rows = await self._fetch_all(
            statement,
            {
                "embedding": vector_text,
                "document_ids": list(scoped_ids),
                "model_id": model_id,
                "dimensions": dimensions,
                "candidate_k": request.vector_candidate_k,
            },
        )
        return tuple(
            StoredCandidate(
                grain=_document_grain(row["grain"]),
                vector_score=_float_value(row["vector_score"], field="vector_score"),
            )
            for row in rows
        )

    async def count_document_grains(self, document_id: str) -> int:
        rows = await self._fetch_all(
            sql.SQL(
                "SELECT count(*) AS grain_count "
                "FROM corpus.document_grain WHERE doc_id = %(document_id)s"
            ),
            {"document_id": document_id},
        )
        return _int_value(rows[0]["grain_count"], field="grain_count")

    async def load_document_grains(self, document_id: str) -> Sequence[DocumentGrain]:
        rows = await self._fetch_all(
            sql.SQL(
                "SELECT to_jsonb(g) AS grain FROM corpus.document_grain AS g "
                "WHERE g.doc_id = %(document_id)s ORDER BY g.grain_id ASC"
            ),
            {"document_id": document_id},
        )
        return tuple(_document_grain(row["grain"]) for row in rows)

    async def load_grains(self, grain_ids: tuple[str, ...]) -> Sequence[DocumentGrain]:
        if not grain_ids:
            return ()
        rows = await self._fetch_all(
            sql.SQL(
                "SELECT to_jsonb(g) AS grain FROM corpus.document_grain AS g "
                "WHERE g.grain_id = ANY(%(grain_ids)s) ORDER BY g.grain_id ASC"
            ),
            {"grain_ids": list(grain_ids)},
        )
        return tuple(_document_grain(row["grain"]) for row in rows)

    async def relations(
        self,
        document_ids: tuple[str, ...],
        *,
        predicate: str,
        direction: RelationDirection,
        as_of: date,
    ) -> Sequence[StoredRelation]:
        if not document_ids:
            return ()
        clauses: list[sql.Composable] = []
        if direction in (RelationDirection.OUTGOING, RelationDirection.BOTH):
            clauses.append(sql.SQL("source_doc_id = ANY(%(document_ids)s)"))
        if direction in (RelationDirection.INCOMING, RelationDirection.BOTH):
            clauses.append(sql.SQL("target_doc_id = ANY(%(document_ids)s)"))
        endpoint_clause = sql.SQL(" OR ").join(clauses)
        statement = sql.SQL(
            """
            SELECT relation_id, source_doc_id, source_grain_ids, predicate,
                   target_doc_id, target_grain_ids
              FROM corpus.document_relation
             WHERE predicate = %(predicate)s
               AND ({endpoint_clause})
             ORDER BY relation_id ASC
            """
        ).format(endpoint_clause=endpoint_clause)
        rows = await self._fetch_all(
            statement,
            {"document_ids": list(document_ids), "predicate": predicate},
        )
        endpoint_ids = tuple(
            dict.fromkeys(
                str(row[key]) for row in rows for key in ("source_doc_id", "target_doc_id")
            )
        )
        allowed = set(await self._scope_resolver.filter_as_of(endpoint_ids, as_of=as_of))
        return tuple(
            StoredRelation(
                relation_id=str(row["relation_id"]),
                source_doc_id=str(row["source_doc_id"]),
                source_grain_ids=_string_tuple(row["source_grain_ids"]),
                predicate=str(row["predicate"]),
                target_doc_id=str(row["target_doc_id"]),
                target_grain_ids=_string_tuple(row["target_grain_ids"]),
            )
            for row in rows
            if str(row["source_doc_id"]) in allowed and str(row["target_doc_id"]) in allowed
        )

    async def discover_grain_relations(
        self,
        grain_ids: tuple[str, ...],
        *,
        as_of: date,
    ) -> Sequence[StoredRelation]:
        if not grain_ids:
            return ()
        rows = await self._fetch_all(
            sql.SQL(
                """
                SELECT relation_id, source_doc_id, source_grain_ids, predicate,
                       target_doc_id, target_grain_ids
                  FROM corpus.document_relation
                 WHERE source_grain_ids && %(grain_ids)s
                    OR target_grain_ids && %(grain_ids)s
                 ORDER BY source_doc_id, predicate, target_doc_id
                """
            ),
            {"grain_ids": list(grain_ids)},
        )
        endpoint_ids = tuple(
            dict.fromkeys(
                str(row[key]) for row in rows for key in ("source_doc_id", "target_doc_id")
            )
        )
        allowed = set(await self._scope_resolver.filter_as_of(endpoint_ids, as_of=as_of))
        return tuple(
            StoredRelation(
                relation_id=str(row["relation_id"]),
                source_doc_id=str(row["source_doc_id"]),
                source_grain_ids=_string_tuple(row["source_grain_ids"]),
                predicate=str(row["predicate"]),
                target_doc_id=str(row["target_doc_id"]),
                target_grain_ids=_string_tuple(row["target_grain_ids"]),
            )
            for row in rows
            if str(row["source_doc_id"]) in allowed and str(row["target_doc_id"]) in allowed
        )

    async def _scope(
        self, request: SearchRequest, document_ids: tuple[str, ...]
    ) -> tuple[str, ...]:
        if document_ids:
            # A relation edge already chose the target document.  Reapplying the
            # original company/type filters could incorrectly discard that edge;
            # only the inclusive as-of boundary remains mandatory here.
            return await self._scope_resolver.filter_as_of(document_ids, as_of=request.as_of)
        return await self._scope_resolver.resolve(request)

    async def _fetch_all(
        self,
        statement: sql.Composable,
        parameters: Mapping[str, object],
    ) -> list[dict[str, object]]:
        async with self._pool.connection() as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(statement, parameters)
                return cast(list[dict[str, object]], await cursor.fetchall())


def _float_value(value: object, *, field: str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    raise RetrievalDataError(f"{field} must be numeric")


def _int_value(value: object, *, field: str) -> int:
    if isinstance(value, int):
        return value
    raise RetrievalDataError(f"{field} must be an integer")


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise RetrievalDataError("grain ids must be a list or tuple")
    return tuple(str(item) for item in value)


def _document_grain(value: object) -> DocumentGrain:
    if not isinstance(value, dict):
        raise RetrievalDataError("document_grain row must be a JSON object")
    payload = dict(value)
    payload["context"] = payload.pop("semantic_context")
    payload["source"] = payload.pop("source_address")
    return DocumentGrain.model_validate(payload)


def _vector_sql(metric: VectorMetric) -> tuple[str, str]:
    if metric == VectorMetric.COSINE:
        return "<=>", "1.0 - "
    if metric == VectorMetric.INNER_PRODUCT:
        return "<#>", "-"
    if metric == VectorMetric.L2:
        return "<->", "-"
    raise RetrievalDataError(f"unsupported vector metric: {metric}")

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph.state import CompiledStateGraph
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from evidence.document_grain import DocumentGrain, GrainKind, SemanticContext, SourceAddress
from evidence.document_relation import RelationPredicate
from reasoning.computing.models import (
    ComputationError,
    ComputationErrorCode,
    ComputationPlan,
    ComputationPlanningResult,
    ComputationResult,
    ComputationStatus,
    ConstantExpression,
    DSLVersion,
    EvidenceReference,
    ExecutionStep,
    Operand,
    OperandBindingResult,
    OperationExpression,
    Primitive,
    ReferenceExpression,
)
from reasoning.core.core_graph import create_main_graph
from reasoning.core.core_models import (
    ComputationIntent,
    CoreVerificationResult,
    OperandRequirement,
    RuntimeFailure,
    VerificationAction,
    VerificationIssue,
)
from reasoning.core.core_state import DisclosureAIInput, DisclosureAIOutput, DisclosureAIState
from reasoning.generate_answer.models import (
    AnswerClaim,
    AnswerVerificationIssue,
    AnswerVerificationResult,
    AnswerVerificationStatus,
    CannotAnswerResponse,
    ClarificationResponse,
    FinalResponse,
)
from reasoning.query_understanding.models import (
    ContextOrigin,
    ContextPoint,
    ContextStatus,
    QuerySafetyResult,
    QueryUnderstanding,
)
from reasoning.retrieval import RetrievalSearchBackend
from reasoning.retrieval.backend import HybridRetrievalBackend
from reasoning.retrieval.config import RetrievalRuntimeConfig
from reasoning.retrieval.model_providers import build_retrieval_models
from reasoning.retrieval.models import (
    EvidenceTarget,
    RelationDirection,
    RelationDiscoveryMode,
    RelationHop,
    RetrievalFrame,
    RetrievalScore,
    RetrievalSearchResult,
    RetrievedEvidence,
    RetrievedGrainRole,
    VersionPolicy,
)
from reasoning.retrieval.postgres import (
    PostgresDocumentScopeResolver,
    PostgresRetrievalStore,
)

from .llm import ClovaModelSettings, build_llms, close_llms


@dataclass(frozen=True)
class ReasoningAppSettings:
    checkpoint_database_url: str
    retrieval_database_url: str
    retrieval: RetrievalRuntimeConfig
    clova: ClovaModelSettings = ClovaModelSettings()
    checkpoint_pool_min_size: int = 1
    checkpoint_pool_max_size: int = 10

    @classmethod
    def from_environment(cls) -> ReasoningAppSettings:
        database_url = os.environ.get("CHECKPOINT_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("CHECKPOINT_DATABASE_URL or DATABASE_URL is required")
        retrieval_database_url = os.environ.get("DATABASE_URL")
        if not retrieval_database_url:
            raise RuntimeError("DATABASE_URL is required for retrieval")
        return cls(
            checkpoint_database_url=database_url,
            retrieval_database_url=retrieval_database_url,
            retrieval=RetrievalRuntimeConfig.from_environment(),
        )

    def __post_init__(self) -> None:
        if self.checkpoint_pool_min_size < 1:
            raise ValueError("checkpoint_pool_min_size must be at least 1")
        if self.checkpoint_pool_max_size < self.checkpoint_pool_min_size:
            raise ValueError("checkpoint_pool_max_size must be at least the minimum")


async def setup_checkpoint_database(database_url: str) -> None:
    async with AsyncPostgresSaver.from_conn_string(
        database_url,
        serde=create_checkpoint_serializer(),
    ) as checkpointer:
        await checkpointer.setup()


@asynccontextmanager
async def reasoning_graph_lifespan(
    settings: ReasoningAppSettings,
    search_backend: RetrievalSearchBackend | None = None,
) -> AsyncIterator[
    CompiledStateGraph[DisclosureAIState, None, DisclosureAIInput, DisclosureAIOutput]
]:
    llms = build_llms(settings.clova)
    checkpoint_pool = cast(
        AsyncConnectionPool[AsyncConnection[dict[str, Any]]],
        cast(
            object,
            AsyncConnectionPool(
                conninfo=settings.checkpoint_database_url,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": 0,
                    "row_factory": dict_row,
                },
                min_size=settings.checkpoint_pool_min_size,
                max_size=settings.checkpoint_pool_max_size,
                open=False,
            ),
        ),
    )
    retrieval_pool: AsyncConnectionPool[Any] | None = None
    try:
        await checkpoint_pool.open()
        await checkpoint_pool.wait()
        checkpointer = AsyncPostgresSaver(
            checkpoint_pool,
            serde=create_checkpoint_serializer(),
        )
        resolved_backend = search_backend
        if resolved_backend is None:
            retrieval_pool = AsyncConnectionPool(
                conninfo=settings.retrieval_database_url,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": 0,
                    "row_factory": dict_row,
                },
                min_size=settings.retrieval.pool_min_size,
                max_size=settings.retrieval.pool_max_size,
                open=False,
            )
            await retrieval_pool.open()
            await retrieval_pool.wait()
            embedding_provider, cross_encoder = await asyncio.to_thread(
                build_retrieval_models,
                settings.retrieval.models,
            )
            scope_resolver = PostgresDocumentScopeResolver(retrieval_pool)
            resolved_backend = HybridRetrievalBackend(
                store=PostgresRetrievalStore(
                    pool=retrieval_pool,
                    scope_resolver=scope_resolver,
                ),
                embedding_provider=embedding_provider,
                cross_encoder=cross_encoder,
                config=settings.retrieval.query,
            )
        assert resolved_backend is not None
        yield create_main_graph(
            llms=llms,
            search_backend=resolved_backend,
            retrieval_query_config=settings.retrieval.query,
            checkpointer=checkpointer,
        )
    finally:
        if retrieval_pool is not None:
            await retrieval_pool.close()
        await checkpoint_pool.close()
        await close_llms(llms)


def create_checkpoint_serializer() -> JsonPlusSerializer:
    return JsonPlusSerializer(pickle_fallback=False).with_msgpack_allowlist(
        [
            OperandRequirement,
            ComputationIntent,
            VerificationAction,
            VerificationIssue,
            CoreVerificationResult,
            RuntimeFailure,
            QuerySafetyResult,
            ContextStatus,
            ContextOrigin,
            ContextPoint,
            QueryUnderstanding,
            EvidenceTarget,
            RetrievalFrame,
            VersionPolicy,
            RelationDirection,
            RelationDiscoveryMode,
            RelationHop,
            RelationPredicate,
            RetrievalScore,
            RetrievedGrainRole,
            RetrievedEvidence,
            RetrievalSearchResult,
            GrainKind,
            SemanticContext,
            SourceAddress,
            DocumentGrain,
            DSLVersion,
            Primitive,
            EvidenceReference,
            Operand,
            OperandBindingResult,
            ReferenceExpression,
            ConstantExpression,
            OperationExpression,
            ComputationPlan,
            ComputationPlanningResult,
            ComputationStatus,
            ComputationErrorCode,
            ComputationError,
            ExecutionStep,
            ComputationResult,
            AnswerClaim,
            ClarificationResponse,
            FinalResponse,
            CannotAnswerResponse,
            AnswerVerificationStatus,
            AnswerVerificationIssue,
            AnswerVerificationResult,
        ]
    )

"""Environment-backed retrieval configuration.

Ranking thresholds are bootstrap values, not claims of quality.  They stay in
configuration so an evaluation run can replace them without code changes.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .retrieval import RetrievalQueryConfig, VectorMetric


class RetrievalModelConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    embedding_model_id: str = Field(default="BAAI/bge-m3", min_length=1)
    embedding_storage_id: str | None = None
    embedding_dimensions: int = Field(default=1024, ge=1, le=2000)
    embedding_batch_size: int = Field(default=32, ge=1)
    embedding_scheduling_window_batches: int = Field(default=8, ge=1)
    embedding_device: str | None = None
    normalize_embeddings: bool = True
    cross_encoder_model_id: str = Field(default="BAAI/bge-reranker-v2-m3", min_length=1)
    cross_encoder_batch_size: int = Field(default=16, ge=1)
    cross_encoder_device: str | None = None
    normalize_cross_encoder_score: bool = True


class RetrievalRuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: RetrievalQueryConfig
    models: RetrievalModelConfig = RetrievalModelConfig()
    pool_min_size: int = Field(default=1, ge=1)
    pool_max_size: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def validate_pool_size(self) -> RetrievalRuntimeConfig:
        if self.pool_max_size < self.pool_min_size:
            raise ValueError("retrieval pool max size must be at least the minimum")
        return self

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> RetrievalRuntimeConfig:
        values = os.environ if environment is None else environment
        return cls(
            query=RetrievalQueryConfig(
                lexical_candidate_k=_integer(values, "RETRIEVAL_LEXICAL_CANDIDATE_K", 50),
                vector_candidate_k=_integer(values, "RETRIEVAL_VECTOR_CANDIDATE_K", 50),
                max_top_k=_integer(values, "RETRIEVAL_MAX_TOP_K", 10),
                minimum_score=_float(values, "RETRIEVAL_MINIMUM_SCORE", 0.5),
                exhaustive_grain_limit=_integer(values, "RETRIEVAL_EXHAUSTIVE_GRAIN_LIMIT", 100),
                rrf_k=_integer(values, "RETRIEVAL_RRF_K", 60),
                vector_metric=VectorMetric(
                    values.get("RETRIEVAL_VECTOR_METRIC", VectorMetric.COSINE.value)
                ),
            ),
            models=RetrievalModelConfig(
                embedding_model_id=values.get("RETRIEVAL_EMBEDDING_MODEL", "BAAI/bge-m3"),
                embedding_dimensions=_integer(values, "RETRIEVAL_EMBEDDING_DIMENSIONS", 1024),
                embedding_storage_id=values.get("RETRIEVAL_EMBEDDING_STORAGE_ID") or None,
                embedding_batch_size=_integer(values, "RETRIEVAL_EMBEDDING_BATCH_SIZE", 32),
                embedding_scheduling_window_batches=_integer(
                    values, "RETRIEVAL_EMBEDDING_SCHEDULING_WINDOW_BATCHES", 8
                ),
                embedding_device=values.get("RETRIEVAL_EMBEDDING_DEVICE") or None,
                normalize_embeddings=_boolean(values, "RETRIEVAL_NORMALIZE_EMBEDDINGS", True),
                cross_encoder_model_id=values.get(
                    "RETRIEVAL_CROSS_ENCODER_MODEL", "BAAI/bge-reranker-v2-m3"
                ),
                cross_encoder_batch_size=_integer(values, "RETRIEVAL_CROSS_ENCODER_BATCH_SIZE", 16),
                cross_encoder_device=values.get("RETRIEVAL_CROSS_ENCODER_DEVICE") or None,
                normalize_cross_encoder_score=_boolean(
                    values, "RETRIEVAL_NORMALIZE_CROSS_ENCODER_SCORE", True
                ),
            ),
            pool_min_size=_integer(values, "RETRIEVAL_POOL_MIN_SIZE", 1),
            pool_max_size=_integer(values, "RETRIEVAL_POOL_MAX_SIZE", 10),
        )


def _integer(values: Mapping[str, str], key: str, default: int) -> int:
    return int(values.get(key, str(default)))


def _float(values: Mapping[str, str], key: str, default: float) -> float:
    return float(values.get(key, str(default)))


def _boolean(values: Mapping[str, str], key: str, default: bool) -> bool:
    raw = values.get(key)
    if raw is None:
        return default
    lowered = raw.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{key} must be a boolean")

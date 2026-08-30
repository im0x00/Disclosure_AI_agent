"""Local, replaceable embedding and reranking model adapters."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Sequence
from typing import Any, cast

from sentence_transformers import CrossEncoder as SentenceCrossEncoder
from sentence_transformers import SentenceTransformer

from .config import RetrievalModelConfig
from .errors import RetrievalConfigurationError


class SentenceTransformerEmbeddingProvider:
    def __init__(self, config: RetrievalModelConfig) -> None:
        self._config = config
        self._model = SentenceTransformer(
            config.embedding_model_id,
            device=config.embedding_device,
        )
        actual_dimensions = self._model.get_embedding_dimension()
        if actual_dimensions != config.embedding_dimensions:
            raise RetrievalConfigurationError(
                "embedding dimension mismatch: "
                f"configured={config.embedding_dimensions} actual={actual_dimensions}"
            )

    @property
    def model_id(self) -> str:
        return self._config.embedding_storage_id or (
            f"{self._config.embedding_model_id}"
            f"::normalized={str(self._config.normalize_embeddings).lower()}"
        )

    @property
    def dimensions(self) -> int:
        return self._config.embedding_dimensions

    @property
    def device(self) -> str:
        return str(self._model.device)

    async def embed_queries(
        self,
        texts: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...]:
        return await self._encode(texts, prompt_name="query")

    async def embed_documents(
        self,
        texts: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...]:
        return await self._encode(texts, prompt_name=None)

    async def _encode(
        self,
        texts: tuple[str, ...],
        *,
        prompt_name: str | None,
    ) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()

        def encode() -> Any:
            arguments: dict[str, object] = {
                "batch_size": self._config.embedding_batch_size,
                "normalize_embeddings": self._config.normalize_embeddings,
                "convert_to_numpy": True,
                "show_progress_bar": False,
            }
            if prompt_name is not None and prompt_name in self._model.prompts:
                arguments["prompt_name"] = prompt_name
            return self._model.encode(list(texts), **arguments)

        values = await asyncio.to_thread(encode)
        rows = values.tolist()
        result = tuple(tuple(float(value) for value in row) for row in rows)
        if any(len(row) != self.dimensions for row in result):
            raise RetrievalConfigurationError("embedding provider returned an invalid dimension")
        return result


class SentenceTransformerCrossEncoder:
    def __init__(self, config: RetrievalModelConfig) -> None:
        self._config = config
        self._model = SentenceCrossEncoder(
            config.cross_encoder_model_id,
            device=config.cross_encoder_device,
        )

    async def score(
        self,
        pairs: tuple[tuple[str, str], ...],
    ) -> tuple[float, ...]:
        if not pairs:
            return ()

        def predict() -> Sequence[object]:
            return cast(
                Sequence[object],
                self._model.predict(
                    list(pairs),
                    batch_size=self._config.cross_encoder_batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                ),
            )

        raw_scores = await asyncio.to_thread(predict)
        scores = tuple(_scalar(value) for value in raw_scores)
        if self._config.normalize_cross_encoder_score:
            return tuple(_sigmoid(value) for value in scores)
        return scores


def build_retrieval_models(
    config: RetrievalModelConfig,
) -> tuple[SentenceTransformerEmbeddingProvider, SentenceTransformerCrossEncoder]:
    return (
        SentenceTransformerEmbeddingProvider(config),
        SentenceTransformerCrossEncoder(config),
    )


def _scalar(value: object) -> float:
    item_method = getattr(value, "item", None)
    if callable(item_method):
        item = item_method()
        if isinstance(item, (float, int)):
            return float(item)
    if isinstance(value, (float, int)):
        return float(value)
    raise RetrievalConfigurationError("cross encoder must return one scalar per pair")


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)

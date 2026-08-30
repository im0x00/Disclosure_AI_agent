from reasoning.retrieval.config import RetrievalRuntimeConfig
from reasoning.retrieval.retrieval import VectorMetric


def test_retrieval_runtime_config_is_environment_replaceable() -> None:
    config = RetrievalRuntimeConfig.from_environment(
        {
            "RETRIEVAL_EMBEDDING_MODEL": "example/embedding",
            "RETRIEVAL_EMBEDDING_DIMENSIONS": "768",
            "RETRIEVAL_EMBEDDING_SCHEDULING_WINDOW_BATCHES": "12",
            "RETRIEVAL_VECTOR_METRIC": "inner_product",
            "RETRIEVAL_CROSS_ENCODER_MODEL": "example/reranker",
            "RETRIEVAL_MINIMUM_SCORE": "0.73",
            "RETRIEVAL_EXHAUSTIVE_GRAIN_LIMIT": "120",
        }
    )

    assert config.models.embedding_model_id == "example/embedding"
    assert config.models.embedding_dimensions == 768
    assert config.models.embedding_scheduling_window_batches == 12
    assert config.query.vector_metric is VectorMetric.INNER_PRODUCT
    assert config.models.cross_encoder_model_id == "example/reranker"
    assert config.query.minimum_score == 0.73
    assert config.query.exhaustive_grain_limit == 120

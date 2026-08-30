import asyncio

import pytest

from reasoning.app_lifecycle import create_checkpoint_serializer
from reasoning.computing.models import ComputationPlanningResult
from reasoning.llm import build_llms, close_llms
from reasoning.query_understanding.models import (
    ContextPoint,
    ContextStatus,
    QueryUnderstanding,
)


def test_checkpoint_serializer_round_trips_allowlisted_state() -> None:
    state = {
        "question": "What is the amount?",
        "query_understanding": QueryUnderstanding(
            question_raw="What is the amount?",
            intention="find amount",
            contextual_points=[
                ContextPoint(
                    key="company",
                    status=ContextStatus.KNOWN,
                    value="Example Corp",
                )
            ],
            needs_clarification=False,
        ),
    }
    serializer = create_checkpoint_serializer()

    restored = serializer.loads_typed(serializer.dumps_typed(state))

    assert restored == state


def test_clova_registry_builds_native_json_schema_runnables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLOVASTUDIO_API_KEY", "nv-test-key")
    registry = build_llms()
    try:
        runnable = registry.reasoning.with_structured_output(
            ComputationPlanningResult,
            method="json_schema",
        )
        assert runnable is not None
    finally:
        asyncio.run(close_llms(registry))

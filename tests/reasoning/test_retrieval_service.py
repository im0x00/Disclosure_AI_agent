import asyncio
from unittest.mock import Mock
from uuid import UUID

from reasoning.query_understanding.models import (
    ContextPoint,
    ContextStatus,
    QueryUnderstanding,
)
from reasoning.retrieval import RetrievalService
from reasoning.retrieval.models import (
    EvidenceTarget,
    RetrievalFrame,
    RetrievedEvidence,
)


def test_plan_preserves_query_understanding() -> None:
    understanding = _understanding()
    target = EvidenceTarget(
        need="Find the disclosure that reports the contract termination",
        supported_by=understanding.contextual_points[0],
    )
    planner = _Planner({"evidence_targets": [target.model_dump()]})
    llm = Mock()
    llm.with_structured_output.return_value = planner
    service = RetrievalService(llm=llm, search_backend=_SearchBackend())

    frame = asyncio.run(service.plan(understanding))

    assert frame.query_understanding is understanding
    assert frame.evidence_targets == [target]


def test_search_returns_one_result_per_target() -> None:
    understanding = _understanding()
    targets = [
        EvidenceTarget(
            need="Find the signed contract disclosure",
            supported_by=understanding.contextual_points[0],
        ),
        EvidenceTarget(
            need="Find the later termination disclosure",
            supported_by=understanding.contextual_points[0],
        ),
    ]
    planner = _Planner({"evidence_targets": []})
    llm = Mock()
    llm.with_structured_output.return_value = planner
    backend = _SearchBackend()
    service = RetrievalService(llm=llm, search_backend=backend)

    results = asyncio.run(
        service.search(
            frame=RetrievalFrame(
                query_understanding=understanding,
                evidence_targets=targets,
            )
        )
    )

    assert [result.target for result in results] == targets
    assert [result.search_results for result in results] == [
        [backend.evidence],
        [backend.evidence],
    ]


class _Planner:
    def __init__(self, result: object) -> None:
        self.result = result

    async def ainvoke(self, _: object) -> object:
        return self.result


class _SearchBackend:
    def __init__(self) -> None:
        self.evidence = RetrievedEvidence(
            document_id="major_20240101000001",
            node_id=UUID("00000000-0000-0000-0000-000000000001"),
            node_type="block",
            text="Contract terminated.",
            source_path="raw/major/example/20240101000001/document.xml",
            start_byte=10,
            end_byte=30,
        )

    async def search(self, _: EvidenceTarget) -> list[RetrievedEvidence]:
        return [self.evidence]


def _understanding() -> QueryUnderstanding:
    return QueryUnderstanding(
        question_raw="Which signed contract was later terminated?",
        intention="Find a signed contract and its later termination",
        contextual_points=[
            ContextPoint(
                key="company",
                status=ContextStatus.KNOWN,
                value="Example Corp",
            )
        ],
        needs_clarification=False,
    )

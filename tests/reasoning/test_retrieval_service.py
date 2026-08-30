import asyncio
from unittest.mock import Mock

from reasoning.query_understanding.models import (
    ContextPoint,
    ContextStatus,
    QueryUnderstanding,
)
from reasoning.retrieval import RetrievalService
from reasoning.retrieval.batch_service import RetrievalBatchService
from reasoning.retrieval.models import (
    EvidenceTarget,
    RetrievalFrame,
    RetrievedEvidence,
    SearchBatchResult,
    SearchRequest,
)
from reasoning.retrieval.retrieval import RetrievalQueryCompiler, RetrievalQueryConfig
from tests.reasoning.retrieval_fixtures import retrieved_evidence


def test_plan_preserves_query_understanding() -> None:
    understanding = _understanding()
    target = EvidenceTarget(
        need="Find the disclosure that reports the contract termination",
        supported_by=understanding.contextual_points[0],
    )
    planner = _Planner({"evidence_targets": [target.model_dump()]})
    llm = Mock()
    llm.with_structured_output.return_value = planner
    service = _service(llm, _SearchBackend())

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
    service = _service(llm, backend)

    results = asyncio.run(
        service.search(
            frame=RetrievalFrame(
                query_understanding=understanding,
                evidence_targets=targets,
            )
        )
    )

    assert [result.target for result in results] == targets
    assert [[item.grain_id for item in result.search_results] for result in results] == [
        ["1" * 64],
        ["1" * 64],
    ]


class _Planner:
    def __init__(self, result: object) -> None:
        self.result = result

    async def ainvoke(self, _: object) -> object:
        return self.result


class _SearchBackend:
    def __init__(self) -> None:
        self.evidence: RetrievedEvidence = retrieved_evidence(
            target_id="target:0",
            document_id="major_20240101000001",
            grain_id="1" * 64,
            text="Contract terminated.",
        )

    async def search_many(
        self,
        requests: tuple[SearchRequest, ...],
    ) -> tuple[SearchBatchResult, ...]:
        return tuple(
            SearchBatchResult(
                request=request,
                hits=(self.evidence.model_copy(update={"target_id": request.target_id}),),
            )
            for request in requests
        )


def _service(llm: Mock, backend: _SearchBackend) -> RetrievalService:
    compiler = RetrievalQueryCompiler(
        RetrievalQueryConfig(
            lexical_candidate_k=10,
            vector_candidate_k=10,
            max_top_k=5,
            minimum_score=0.5,
            exhaustive_grain_limit=20,
        )
    )
    return RetrievalService(
        llm=llm,
        batch_service=RetrievalBatchService(
            query_compiler=compiler,
            search_backend=backend,
        ),
    )


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

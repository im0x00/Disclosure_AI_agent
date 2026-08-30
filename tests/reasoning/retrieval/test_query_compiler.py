from datetime import date

from reasoning.query_understanding.models import (
    ContextOrigin,
    ContextPoint,
    ContextStatus,
    QueryUnderstanding,
)
from reasoning.retrieval.models import EvidenceTarget, RetrievalFrame
from reasoning.retrieval.retrieval import RetrievalQueryCompiler, RetrievalQueryConfig


def test_only_explicit_known_context_becomes_a_hard_filter() -> None:
    inferred_company = ContextPoint(
        key="company",
        status=ContextStatus.INFERRED,
        origin=ContextOrigin.INFERRED,
        value="Guessed Corp",
    )
    explicit_group = ContextPoint(
        key="doc_group",
        status=ContextStatus.KNOWN,
        origin=ContextOrigin.EXPLICIT,
        value="major",
    )
    understanding = QueryUnderstanding(
        question_raw="Find the contract amount",
        intention="find contract amount",
        contextual_points=[inferred_company, explicit_group],
        needs_clarification=False,
    )
    compiler = RetrievalQueryCompiler(
        RetrievalQueryConfig(
            lexical_candidate_k=10,
            vector_candidate_k=10,
            max_top_k=5,
            minimum_score=0.5,
            exhaustive_grain_limit=20,
        )
    )

    request = compiler.compile(
        RetrievalFrame(
            query_understanding=understanding,
            evidence_targets=[
                EvidenceTarget(need="contract amount", supported_by=inferred_company)
            ],
        ),
        today=date(2025, 1, 1),
    )[0]

    assert request.filters.company_names == ()
    assert request.filters.doc_groups == ("major",)

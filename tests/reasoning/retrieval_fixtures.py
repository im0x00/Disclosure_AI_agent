from evidence.document_grain import (
    DocumentGrain,
    GrainKind,
    SemanticContext,
    SourceAddress,
)
from reasoning.retrieval.models import (
    RetrievalScore,
    RetrievedEvidence,
    RetrievedGrainRole,
)


def retrieved_evidence(
    *,
    document_id: str,
    grain_id: str,
    text: str,
    target_id: str = "target:0",
) -> RetrievedEvidence:
    return RetrievedEvidence(
        target_id=target_id,
        grain=DocumentGrain.model_construct(
            schema_version="1.0",
            compiler_version="1.0",
            grain_id=grain_id,
            doc_id=document_id,
            kind=GrainKind.PROSE,
            core_text=text,
            rendered_text=text,
            estimated_tokens=1,
            context=SemanticContext(),
            source=SourceAddress.model_construct(
                artifact_id="test-artifact",
                source_path="test.xml",
                ordinal=0,
                scope_id="0" * 64,
                core_ranges=(),
                context_ranges=(),
            ),
            previous_grain_id=None,
            next_grain_id=None,
        ),
        role=RetrievedGrainRole.PRIMARY,
        rank=1,
        scores=RetrievalScore(cross_encoder=0.9),
    )

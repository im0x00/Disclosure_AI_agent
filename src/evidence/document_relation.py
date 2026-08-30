from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from evidence.document_grain import DocumentGrain
from evidence.document_tree import DocumentTree, walk_nodes

GrainId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class RelationPredicate(StrEnum):
    REVISES = "revises"
    REFERENCES = "references"
    TERMINATES = "terminates"


class RelationSignal(StrEnum):
    IS_CORRECTION = "is_correction"
    RELATED_DISCLOSURE = "related_disclosure"
    TERMINATION = "termination"


SIGNAL_PREDICATES: Mapping[str, RelationPredicate] = MappingProxyType(
    {
        RelationSignal.IS_CORRECTION: RelationPredicate.REVISES,
        RelationSignal.RELATED_DISCLOSURE: RelationPredicate.REFERENCES,
        RelationSignal.TERMINATION: RelationPredicate.TERMINATES,
    }
)


class UnsupportedRelationSignals(ValueError):
    def __init__(self, signals: Iterable[str]) -> None:
        self.signals = tuple(sorted(set(signals)))
        super().__init__("relation signals have no predicate: " + ", ".join(self.signals))


class DocumentRelation(BaseModel):
    """One directed, in-corpus relation with optional grain endpoints.

    An empty grain-id tuple means that the endpoint is the whole document.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_doc_id: str = Field(pattern=r"^[a-z][a-z0-9-]*_[0-9]{14}$")
    source_grain_ids: tuple[GrainId, ...] = ()
    predicate: RelationPredicate
    target_doc_id: str = Field(pattern=r"^[a-z][a-z0-9-]*_[0-9]{14}$")
    target_grain_ids: tuple[GrainId, ...] = ()

    @model_validator(mode="after")
    def validate_endpoints(self) -> DocumentRelation:
        if self.source_doc_id == self.target_doc_id:
            raise ValueError("a document relation must connect two different documents")
        if len(self.source_grain_ids) != len(set(self.source_grain_ids)):
            raise ValueError("source_grain_ids must not contain duplicates")
        if len(self.target_grain_ids) != len(set(self.target_grain_ids)):
            raise ValueError("target_grain_ids must not contain duplicates")
        return self


def require_predicate_coverage(signals: Iterable[str]) -> None:
    """Fail when discovery observes a relation signal without a predicate."""

    missing = set(signals) - set(SIGNAL_PREDICATES)
    if missing:
        raise UnsupportedRelationSignals(missing)


def predicate_for_signal(signal: str) -> RelationPredicate:
    require_predicate_coverage((signal,))
    return SIGNAL_PREDICATES[signal]


def manifest_relation_signals(document: Mapping[str, object]) -> frozenset[str]:
    """Return relation-bearing signals available without parsing a document tree."""

    signals: set[str] = set()
    if document.get("is_correction") is True:
        signals.add(RelationSignal.IS_CORRECTION)

    report_name = str(document.get("report_name") or document.get("report_nm") or "")
    doc_subtype = str(document.get("doc_subtype") or "")
    if "해지" in report_name or "해지" in doc_subtype:
        signals.add(RelationSignal.TERMINATION)
    return frozenset(signals)


def tree_relation_signals(tree: DocumentTree) -> frozenset[str]:
    """Return relation-bearing signals preserved in the compiled tree."""

    signals: set[str] = set()
    for artifact in tree.artifacts:
        for node in walk_nodes(artifact.root):
            if node.source_tag.lower() == "correction":
                signals.add(RelationSignal.IS_CORRECTION)
            attribute_values = " ".join(attribute.value.lower() for attribute in node.attributes)
            if "rcpno=" in attribute_values or "acptno=" in attribute_values:
                signals.add(RelationSignal.RELATED_DISCLOSURE)
    return frozenset(signals)


def validate_relation_grains(
    relation: DocumentRelation,
    *,
    grains_by_id: Mapping[str, DocumentGrain],
) -> None:
    """Check optional grain endpoints against the current compiled grain set."""

    endpoints = (
        ("source", relation.source_doc_id, relation.source_grain_ids),
        ("target", relation.target_doc_id, relation.target_grain_ids),
    )
    for endpoint, doc_id, grain_ids in endpoints:
        grains: list[DocumentGrain] = []
        for grain_id in grain_ids:
            grain = grains_by_id.get(grain_id)
            if grain is None:
                raise ValueError(f"{endpoint}_grain_ids contains an unknown grain_id")
            if grain.doc_id != doc_id:
                raise ValueError(f"{endpoint}_grain_ids contains a grain owned by another document")
            grains.append(grain)

        ordinals = [grain.source.ordinal for grain in grains]
        if ordinals != sorted(ordinals):
            raise ValueError(f"{endpoint}_grain_ids must follow document order")


def relations_affected_by_grain_rebuild(
    relations: Iterable[DocumentRelation],
    rebuilt_doc_ids: Iterable[str],
) -> tuple[DocumentRelation, ...]:
    """Return edges that must be rebuilt after selected documents are recompiled."""

    rebuilt = frozenset(rebuilt_doc_ids)
    return tuple(
        relation
        for relation in relations
        if relation.source_doc_id in rebuilt or relation.target_doc_id in rebuilt
    )

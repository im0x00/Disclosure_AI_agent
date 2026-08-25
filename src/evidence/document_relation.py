from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evidence.document_tree import DocumentTree, NodeKind, SourceRange, walk_nodes


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
    """One directed, in-corpus relation with optional subtree endpoints.

    A missing anchor means that the endpoint is the whole document.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_doc_id: str = Field(pattern=r"^[a-z][a-z0-9-]*_[0-9]{14}$")
    predicate: RelationPredicate
    target_doc_id: str = Field(pattern=r"^[a-z][a-z0-9-]*_[0-9]{14}$")
    source_anchor: SourceRange | None = None
    target_anchor: SourceRange | None = None

    @model_validator(mode="after")
    def reject_self_relation(self) -> DocumentRelation:
        if self.source_doc_id == self.target_doc_id:
            raise ValueError("a document relation must connect two different documents")
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
            if node.kind != NodeKind.LINK:
                continue
            href = next(
                (
                    attribute.value
                    for attribute in node.attributes
                    if attribute.name.lower() == "href"
                ),
                "",
            ).lower()
            if "rcpno=" in href or "acptno=" in href:
                signals.add(RelationSignal.RELATED_DISCLOSURE)
    return frozenset(signals)


def validate_relation_anchors(
    relation: DocumentRelation,
    *,
    source_tree: DocumentTree,
    target_tree: DocumentTree,
) -> None:
    """Check document identities and optional anchors against immutable trees."""

    if source_tree.doc_id != relation.source_doc_id:
        raise ValueError("source tree does not match source_doc_id")
    if target_tree.doc_id != relation.target_doc_id:
        raise ValueError("target tree does not match target_doc_id")

    checks = (
        ("source", relation.source_anchor, source_tree),
        ("target", relation.target_anchor, target_tree),
    )
    for endpoint, anchor, tree in checks:
        if anchor is None:
            continue
        node_ranges = {
            node.source for artifact in tree.artifacts for node in walk_nodes(artifact.root)
        }
        if anchor not in node_ranges:
            raise ValueError(f"{endpoint}_anchor is not a node in its document tree")

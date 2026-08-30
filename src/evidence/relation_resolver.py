from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from evidence.document_grain import DocumentGrain
from evidence.document_relation import DocumentRelation, RelationPredicate
from evidence.document_tree import DocumentTree, Node, SourceRange, Text, walk_nodes

_RECEIPT_PARAMETER = re.compile(r"(rcpno|acptno)=([0-9]{14})", re.IGNORECASE)
_CORRECTION_PREFIX = re.compile(r"^(?:\s*\[[^]]*정정[^]]*]\s*)+")
_NON_WORD = re.compile(r"[^0-9A-Za-z가-힣]+")
_CORRECTION_MARKERS = ("정정신고", "정정관련공시서류", "정정대상공시서류")
_ORIGINAL_FILING_DATE = re.compile(
    r"(?:최초제출일|공시서류제출일|최초보고일).{0,160}?"
    r"([12][0-9]{3})\s*[년./-]\s*([0-9]{1,2})\s*[월./-]\s*([0-9]{1,2})",
    re.DOTALL,
)
_DEFAULT_REVIEW_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "relation-review"
    / "correction-comparisons.jsonl"
)


@dataclass(frozen=True, slots=True)
class RelationDocument:
    """Catalog fields needed by deterministic relation rules."""

    doc_id: str
    receipt_no: str
    corp_code: str
    doc_group: str
    doc_subtype: str | None
    report_name: str
    is_correction: bool
    filer_name: str
    base_year: int | None = None
    base_month: int | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> RelationDocument:
        """Adapt either loader field names or raw manifest field names."""

        return cls(
            doc_id=_required_text(value, "doc_id"),
            receipt_no=_required_text(value, "receipt_no", "rcept_no"),
            corp_code=_required_text(value, "corp_code"),
            doc_group=_required_text(value, "doc_group"),
            doc_subtype=_optional_text(value.get("doc_subtype")),
            report_name=_required_text(value, "report_name", "report_nm"),
            is_correction=value.get("is_correction") is True,
            filer_name=_required_text(value, "filer_name", "flr_nm"),
            base_year=_optional_int(value.get("base_year")),
            base_month=_optional_int(value.get("base_month")),
        )


class RelationCatalog:
    """In-corpus document lookup used while relations are rebuilt."""

    def __init__(self, documents: Iterable[RelationDocument]) -> None:
        self.documents = tuple(documents)
        self._by_receipt_no: dict[str, RelationDocument] = {}
        for document in self.documents:
            if document.receipt_no in self._by_receipt_no:
                raise ValueError(f"duplicate receipt number: {document.receipt_no}")
            self._by_receipt_no[document.receipt_no] = document

    @classmethod
    def from_mappings(cls, values: Iterable[Mapping[str, object]]) -> RelationCatalog:
        return cls(RelationDocument.from_mapping(value) for value in values)

    def by_receipt_no(self, receipt_no: str) -> RelationDocument | None:
        return self._by_receipt_no.get(receipt_no)

    def by_linked_receipt_no(self, receipt_no: str) -> RelationDocument | None:
        """Resolve exact DART receipts, then the KRX exchange receipt alias."""

        exact = self.by_receipt_no(receipt_no)
        if exact is not None or len(receipt_no) != 14:
            return exact
        exchange_alias = self.by_receipt_no(f"{receipt_no[:8]}8{receipt_no[9:]}")
        if exchange_alias is None or exchange_alias.doc_group != "exchange":
            return None
        return exchange_alias


@dataclass(frozen=True, slots=True)
class LinkedReceiptAnchor:
    receipt_no: str
    source: SourceRange


@dataclass(frozen=True, slots=True)
class RelationResolutionContext:
    source_document: RelationDocument
    source_tree: DocumentTree | None
    source_grains: tuple[DocumentGrain, ...]
    catalog: RelationCatalog
    grains_by_doc_id: Mapping[str, tuple[DocumentGrain, ...]]
    trees_by_doc_id: Mapping[str, DocumentTree] = field(default_factory=dict)
    linked_receipts: tuple[LinkedReceiptAnchor, ...] | None = None
    filing_dates_by_doc_id: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    correction_grain_ids: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.source_tree is not None and self.source_tree.doc_id != self.source_document.doc_id:
            raise ValueError("source tree does not match source document")
        if any(grain.doc_id != self.source_document.doc_id for grain in self.source_grains):
            raise ValueError("source grains do not match source document")


class UnresolvedReason(StrEnum):
    NO_IN_CORPUS_CANDIDATE = "no_in_corpus_candidate"
    AMBIGUOUS_CANDIDATES = "ambiguous_candidates"
    REVIEWED_NO_MATCH = "reviewed_no_match"


@dataclass(frozen=True, slots=True)
class UnresolvedRelation:
    source_doc_id: str
    predicate: RelationPredicate
    reason: UnresolvedReason
    candidate_doc_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RuleResolution:
    relations: tuple[DocumentRelation, ...] = ()
    unresolved: tuple[UnresolvedRelation, ...] = ()


@dataclass(frozen=True, slots=True)
class RelationResolution:
    relations: tuple[DocumentRelation, ...] = ()
    unresolved: tuple[UnresolvedRelation, ...] = ()


@dataclass(frozen=True, slots=True)
class ManualRelationReview:
    """A human-reviewed outcome for one exact candidate set."""

    source_doc_id: str
    predicate: RelationPredicate
    candidate_doc_ids: tuple[str, ...]
    selected_target_doc_id: str | None
    rationale: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> ManualRelationReview:
        candidate_doc_ids = _required_text_list(value, "candidate_doc_ids")
        selected_target_doc_id = _optional_text(value.get("selected_target_doc_id"))
        if selected_target_doc_id is not None and selected_target_doc_id not in candidate_doc_ids:
            raise ValueError("manual review target must be one of its candidates")
        return cls(
            source_doc_id=_required_text(value, "source_doc_id"),
            predicate=RelationPredicate(_required_text(value, "predicate")),
            candidate_doc_ids=candidate_doc_ids,
            selected_target_doc_id=selected_target_doc_id,
            rationale=_required_text(value, "rationale"),
        )


class ManualRelationReviews:
    """Read-only human decisions used after deterministic matching abstains."""

    def __init__(self, reviews: Iterable[ManualRelationReview] = ()) -> None:
        self._reviews: dict[tuple[str, RelationPredicate], ManualRelationReview] = {}
        for review in reviews:
            key = (review.source_doc_id, review.predicate)
            if key in self._reviews:
                raise ValueError(f"duplicate manual relation review: {key}")
            self._reviews[key] = review

    @classmethod
    def from_jsonl(cls, path: Path) -> ManualRelationReviews:
        reviews: list[ManualRelationReview] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"manual review line {line_number} must be an object")
            reviews.append(ManualRelationReview.from_mapping(value))
        return cls(reviews)

    @classmethod
    def default(cls) -> ManualRelationReviews:
        return cls.from_jsonl(_DEFAULT_REVIEW_PATH) if _DEFAULT_REVIEW_PATH.exists() else cls()

    def choose(
        self,
        source_doc_id: str,
        predicate: RelationPredicate,
        candidate_doc_ids: Iterable[str],
    ) -> str | None:
        review = self._reviews.get((source_doc_id, predicate))
        if review is None:
            return None
        if frozenset(review.candidate_doc_ids) != frozenset(candidate_doc_ids):
            return None
        return review.selected_target_doc_id

    def matching_review(
        self,
        source_doc_id: str,
        predicate: RelationPredicate,
        candidate_doc_ids: Iterable[str],
    ) -> ManualRelationReview | None:
        review = self._reviews.get((source_doc_id, predicate))
        if review is None:
            return None
        if frozenset(review.candidate_doc_ids) != frozenset(candidate_doc_ids):
            return None
        return review


class RelationResolverRule(Protocol):
    @property
    def skip_when_predicate_resolved(self) -> RelationPredicate | None: ...

    def resolve(self, context: RelationResolutionContext) -> RuleResolution: ...


@dataclass(frozen=True, slots=True)
class ExplicitReceiptLinkRule:
    """Resolve in-corpus receipt links and attach their exact source grains."""

    skip_when_predicate_resolved: RelationPredicate | None = None

    def resolve(self, context: RelationResolutionContext) -> RuleResolution:
        relations: list[DocumentRelation] = []
        linked: list[tuple[SourceRange, RelationDocument, tuple[str, ...]]] = []

        for anchor in _context_linked_receipts(context):
            receipt_no = anchor.receipt_no
            target = context.catalog.by_linked_receipt_no(receipt_no)
            if target is None or target.doc_id == context.source_document.doc_id:
                continue
            source_grain_ids = grain_ids_overlapping_range(
                anchor.source,
                context.source_grains,
            )
            linked.append((anchor.source, target, source_grain_ids))
        # REFERENCE
        linked_by_target: dict[
            str, list[tuple[SourceRange, RelationDocument, tuple[str, ...]]]
        ] = {}
        for item in linked:
            linked_by_target.setdefault(item[1].doc_id, []).append(item)
        for target_items in linked_by_target.values():
            target = target_items[0][1]
            source_grain_ids = _ordered_grain_ids(
                context.source_grains,
                (grain_id for _, _, grain_ids in target_items for grain_id in grain_ids),
            )
            relations.append(
                DocumentRelation(
                    source_doc_id=context.source_document.doc_id,
                    source_grain_ids=source_grain_ids,
                    predicate=RelationPredicate.REFERENCES,
                    target_doc_id=target.doc_id,
                )
            )
        # REVISE
        revision_candidates = tuple(
            item
            for item in linked
            if item[1].receipt_no < context.source_document.receipt_no
            and _same_logical_report(context.source_document, item[1])
        )
        if revision_candidates:
            _, target, link_grain_ids = max(
                revision_candidates,
                key=lambda item: item[1].receipt_no,
            )
            source_grain_ids = _ordered_grain_ids(
                context.source_grains,
                (
                    *_context_correction_grain_ids(context),
                    *link_grain_ids,
                ),
            )
            relations.append(
                DocumentRelation(
                    source_doc_id=context.source_document.doc_id,
                    source_grain_ids=source_grain_ids,
                    predicate=RelationPredicate.REVISES,
                    target_doc_id=target.doc_id,
                )
            )
        # TERMINATE
        termination_candidates = tuple(
            item
            for item in linked
            if item[1].receipt_no < context.source_document.receipt_no
            and _is_termination(context.source_document)
            and _is_signed_contract(item[1])
        )
        if termination_candidates:
            _, target, source_grain_ids = max(
                termination_candidates,
                key=lambda item: item[1].receipt_no,
            )
            relations.append(
                DocumentRelation(
                    source_doc_id=context.source_document.doc_id,
                    source_grain_ids=source_grain_ids,
                    predicate=RelationPredicate.TERMINATES,
                    target_doc_id=target.doc_id,
                )
            )
        return RuleResolution(relations=tuple(relations))


@dataclass(frozen=True, slots=True)
class CorrectionHistoryRule:
    """Resolve one-candidate histories directly and every ambiguity by human review."""

    skip_when_predicate_resolved: RelationPredicate | None = RelationPredicate.REVISES
    manual_reviews: ManualRelationReviews = ManualRelationReviews()

    def resolve(self, context: RelationResolutionContext) -> RuleResolution:
        source = context.source_document
        if not source.is_correction:
            return RuleResolution()

        logical_candidates = tuple(
            document
            for document in context.catalog.documents
            if document.receipt_no < source.receipt_no and _same_logical_report(source, document)
        )
        filing_dates = _context_filing_dates(context, source.doc_id)
        candidates = tuple(
            document
            for document in logical_candidates
            if not filing_dates
            or document.receipt_no[:8] in filing_dates
            or bool(
                frozenset(filing_dates)
                & frozenset(_candidate_original_filing_dates(context, document.doc_id))
            )
        )
        if not candidates:
            return RuleResolution(
                unresolved=(
                    UnresolvedRelation(
                        source_doc_id=source.doc_id,
                        predicate=RelationPredicate.REVISES,
                        reason=UnresolvedReason.NO_IN_CORPUS_CANDIDATE,
                        candidate_doc_ids=tuple(document.doc_id for document in logical_candidates),
                    ),
                )
            )

        deterministic_target = _deterministic_predecessor(candidates, filing_dates)
        ordered_candidates = tuple(
            sorted(candidates, key=lambda candidate: candidate.receipt_no, reverse=True)
        )
        selected = deterministic_target
        if selected is None:
            review = self.manual_reviews.matching_review(
                source.doc_id,
                RelationPredicate.REVISES,
                (candidate.doc_id for candidate in ordered_candidates),
            )
            if review is not None and review.selected_target_doc_id is None:
                return RuleResolution(
                    unresolved=(
                        UnresolvedRelation(
                            source_doc_id=source.doc_id,
                            predicate=RelationPredicate.REVISES,
                            reason=UnresolvedReason.REVIEWED_NO_MATCH,
                            candidate_doc_ids=tuple(
                                candidate.doc_id for candidate in ordered_candidates
                            ),
                        ),
                    )
                )
            selected_doc_id = review.selected_target_doc_id if review is not None else None
            selected = next(
                (
                    candidate
                    for candidate in ordered_candidates
                    if candidate.doc_id == selected_doc_id
                ),
                None,
            )
        if selected is None:
            return RuleResolution(
                unresolved=(
                    UnresolvedRelation(
                        source_doc_id=source.doc_id,
                        predicate=RelationPredicate.REVISES,
                        reason=UnresolvedReason.AMBIGUOUS_CANDIDATES,
                        candidate_doc_ids=tuple(
                            candidate.doc_id for candidate in ordered_candidates
                        ),
                    ),
                )
            )

        source_grain_ids = _ordered_grain_ids(
            context.source_grains,
            _context_correction_grain_ids(context),
        )
        return RuleResolution(
            relations=(
                DocumentRelation(
                    source_doc_id=source.doc_id,
                    source_grain_ids=source_grain_ids,
                    predicate=RelationPredicate.REVISES,
                    target_doc_id=selected.doc_id,
                ),
            )
        )


class DocumentRelationResolver:
    """Run registered rules and return de-duplicated, source-ordered edges."""

    def __init__(
        self,
        rules: Iterable[RelationResolverRule] | None = None,
        *,
        manual_reviews: ManualRelationReviews | None = None,
    ) -> None:
        reviews = manual_reviews if manual_reviews is not None else ManualRelationReviews.default()
        default_rules: tuple[RelationResolverRule, ...] = (
            ExplicitReceiptLinkRule(),
            CorrectionHistoryRule(manual_reviews=reviews),
        )
        self.rules: tuple[RelationResolverRule, ...] = tuple(
            rules if rules is not None else default_rules
        )

    def resolve(self, context: RelationResolutionContext) -> tuple[DocumentRelation, ...]:
        return self.resolve_detailed(context).relations

    def resolve_detailed(self, context: RelationResolutionContext) -> RelationResolution:
        relations: list[DocumentRelation] = []
        unresolved: list[UnresolvedRelation] = []
        for rule in self.rules:
            predicate = rule.skip_when_predicate_resolved
            if predicate is not None and any(
                relation.predicate == predicate for relation in relations
            ):
                continue
            result = rule.resolve(context)
            relations.extend(result.relations)
            unresolved.extend(result.unresolved)
        return RelationResolution(
            relations=tuple(dict.fromkeys(relations)),
            unresolved=tuple(dict.fromkeys(unresolved)),
        )


def grain_ids_overlapping_range(
    source: SourceRange,
    grains: Iterable[DocumentGrain],
) -> tuple[str, ...]:
    """Map exact source evidence only to grains that contain it as core content."""

    ordered = tuple(sorted(grains, key=lambda grain: grain.source.ordinal))
    return tuple(
        grain.grain_id
        for grain in ordered
        if any(_ranges_overlap(source, item) for item in grain.source.core_ranges)
    )


def _required_text(value: Mapping[str, object], *names: str) -> str:
    for name in names:
        item = value.get(name)
        if isinstance(item, str) and item:
            return item
    raise ValueError(f"missing required catalog field: {'/'.join(names)}")


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("catalog period fields must be integers or null")
    return value


def _required_text_list(value: Mapping[str, object], name: str) -> tuple[str, ...]:
    item = value.get(name)
    if (
        not isinstance(item, list)
        or not item
        or not all(isinstance(entry, str) and entry for entry in item)
    ):
        raise ValueError(f"missing required string list: {name}")
    return tuple(item)


def linked_receipt_no(node: Node) -> str | None:
    parameters = {
        name.lower(): receipt_no
        for attribute in node.attributes
        for name, receipt_no in _RECEIPT_PARAMETER.findall(attribute.value)
    }
    return parameters.get("rcpno") or parameters.get("acptno")


def linked_receipt_nodes(tree: DocumentTree) -> tuple[tuple[Node, str], ...]:
    """Return nodes whose attributes carry a DART/KRX receipt parameter."""

    return tuple(
        (node, receipt_no)
        for artifact in tree.artifacts
        for node in walk_nodes(artifact.root)
        if (receipt_no := linked_receipt_no(node)) is not None
    )


def linked_receipt_numbers(tree: DocumentTree) -> tuple[str, ...]:
    """Return linked DART/KIND receipt numbers in source order without duplicates."""

    return tuple(dict.fromkeys(receipt_no for _, receipt_no in linked_receipt_nodes(tree)))


def _node_text(node: Node) -> str:
    parts: list[str] = []
    for item in node.content:
        if isinstance(item, Text):
            parts.append(item.display_value)
        else:
            parts.append(_node_text(item))
    return " ".join(part for part in parts if part)


def _original_filing_dates(tree: DocumentTree) -> tuple[str, ...]:
    text = " ".join(_node_text(artifact.root) for artifact in tree.artifacts)
    return _original_filing_dates_from_text(text)


def _original_filing_dates_from_grains(
    grains: Iterable[DocumentGrain],
) -> tuple[str, ...]:
    return _original_filing_dates_from_text(" ".join(grain.core_text for grain in grains))


def _candidate_original_filing_dates(
    context: RelationResolutionContext,
    doc_id: str,
) -> tuple[str, ...]:
    stored = context.filing_dates_by_doc_id.get(doc_id)
    if stored is not None:
        return stored
    tree = context.trees_by_doc_id.get(doc_id)
    if tree is not None:
        return _original_filing_dates(tree)
    return _original_filing_dates_from_grains(context.grains_by_doc_id.get(doc_id, ()))


def _original_filing_dates_from_text(text: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            f"{int(year):04d}{int(month):02d}{int(day):02d}"
            for year, month, day in _ORIGINAL_FILING_DATE.findall(text)
        )
    )


def original_filing_dates(text: str) -> tuple[str, ...]:
    """Extract normalized original-filing dates from preserved document text."""

    return _original_filing_dates_from_text(text)


def _deterministic_predecessor(
    candidates: tuple[RelationDocument, ...],
    filing_dates: tuple[str, ...],
) -> RelationDocument | None:
    if len(candidates) == 1:
        return candidates[0]
    roots = tuple(
        candidate
        for candidate in candidates
        if not candidate.is_correction and candidate.receipt_no[:8] in filing_dates
    )
    if len(roots) != 1:
        return None
    return max(candidates, key=lambda candidate: candidate.receipt_no)


def _normalized(value: str) -> str:
    return _NON_WORD.sub("", value).lower()


def _normalized_report_name(value: str) -> str:
    return _normalized(_CORRECTION_PREFIX.sub("", value))


def relation_series_key(
    document: RelationDocument,
) -> tuple[str, str, str | None, str, int | None, int | None, str]:
    """Return the catalog identity shared by versions of one logical filing."""

    return (
        document.corp_code,
        document.doc_group,
        document.doc_subtype,
        document.filer_name,
        document.base_year,
        document.base_month,
        _normalized_report_name(document.report_name),
    )


def _same_logical_report(source: RelationDocument, target: RelationDocument) -> bool:
    return source.is_correction and relation_series_key(source) == relation_series_key(target)


def _is_termination(document: RelationDocument) -> bool:
    return "해지" in document.report_name or "해지" in (document.doc_subtype or "")


def _is_signed_contract(document: RelationDocument) -> bool:
    label = f"{document.report_name} {document.doc_subtype or ''}"
    return "체결" in label and "해지" not in label


def _ranges_overlap(left: SourceRange, right: SourceRange) -> bool:
    return (
        left.artifact_id == right.artifact_id
        and left.source_path == right.source_path
        and left.start_byte < right.end_byte
        and right.start_byte < left.end_byte
    )


def _ordered_grain_ids(
    grains: Iterable[DocumentGrain],
    grain_ids: Iterable[str],
) -> tuple[str, ...]:
    selected = frozenset(grain_ids)
    return tuple(
        grain.grain_id
        for grain in sorted(grains, key=lambda item: item.source.ordinal)
        if grain.grain_id in selected
    )


def _correction_grain_ids(
    tree: DocumentTree,
    grains: tuple[DocumentGrain, ...],
) -> tuple[str, ...]:
    tagged = tuple(
        node.source
        for artifact in tree.artifacts
        for node in walk_nodes(artifact.root)
        if node.source_tag.lower() == "correction"
    )
    resolved = tuple(
        dict.fromkeys(
            grain_id
            for source in tagged
            for grain_id in grain_ids_overlapping_range(source, grains)
        )
    )
    if resolved:
        return resolved

    return tuple(
        grain.grain_id
        for grain in grains
        if any(marker in _normalized(grain.core_text) for marker in _CORRECTION_MARKERS)
    )


def _context_linked_receipts(
    context: RelationResolutionContext,
) -> tuple[LinkedReceiptAnchor, ...]:
    if context.linked_receipts is not None:
        return context.linked_receipts
    if context.source_tree is None:
        return ()
    return tuple(
        LinkedReceiptAnchor(receipt_no=receipt_no, source=node.source)
        for node, receipt_no in linked_receipt_nodes(context.source_tree)
    )


def _context_filing_dates(
    context: RelationResolutionContext,
    doc_id: str,
) -> tuple[str, ...]:
    stored = context.filing_dates_by_doc_id.get(doc_id)
    if stored is not None:
        return stored
    if context.source_tree is None:
        return ()
    return _original_filing_dates(context.source_tree)


def _context_correction_grain_ids(
    context: RelationResolutionContext,
) -> tuple[str, ...]:
    if context.correction_grain_ids is not None:
        return context.correction_grain_ids
    if context.source_tree is None:
        return ()
    return _correction_grain_ids(context.source_tree, context.source_grains)


def has_correction_marker(text: str) -> bool:
    return any(marker in _normalized(text) for marker in _CORRECTION_MARKERS)

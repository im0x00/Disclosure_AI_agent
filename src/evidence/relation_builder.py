from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from evidence.compiler import compile_document_tree
from evidence.document_grain import DocumentGrain, SourceAddress
from evidence.document_relation import (
    DocumentRelation,
    RelationPredicate,
    RelationSignal,
    manifest_relation_signals,
    require_predicate_coverage,
    tree_relation_signals,
    validate_relation_grains,
)
from evidence.document_tree import DocumentTree, SourceRange
from evidence.grain_compiler import DEFAULT_MAX_ESTIMATED_TOKENS, compile_document_grains
from evidence.loader import (
    DEFAULT_DATABASE_URL,
    index_document_directories,
    nfc,
    read_documents,
)
from evidence.relation_resolver import (
    DocumentRelationResolver,
    LinkedReceiptAnchor,
    ManualRelationReviews,
    RelationCatalog,
    RelationDocument,
    RelationResolutionContext,
    UnresolvedRelation,
    has_correction_marker,
    linked_receipt_numbers,
    original_filing_dates,
    relation_series_key,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
POOL_QUEUE_FACTOR = 2
INTERRUPTED_RETRIES = 5


@dataclass(frozen=True, slots=True)
class RelationBuildTask:
    doc_id: str
    directory: Path
    corpus_root: Path
    max_estimated_tokens: int = DEFAULT_MAX_ESTIMATED_TOKENS
    cache_directory: Path | None = None


@dataclass(frozen=True, slots=True)
class ScannedRelationDocument:
    doc_id: str
    signals: tuple[str, ...]
    linked_receipt_nos: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CachedRelationDocument:
    doc_id: str
    grains: int


@dataclass(frozen=True, slots=True)
class RelationBuildReport:
    documents_scanned: int
    relation_sources: int
    documents_compiled_with_grains: int
    relations: int
    unresolved: int
    unresolved_by_reason: Mapping[str, int]
    relations_path: Path
    unresolved_path: Path

    def as_json_value(self) -> dict[str, object]:
        return {
            "documents_scanned": self.documents_scanned,
            "relation_sources": self.relation_sources,
            "documents_compiled_with_grains": self.documents_compiled_with_grains,
            "relations": self.relations,
            "unresolved": self.unresolved,
            "unresolved_by_reason": dict(self.unresolved_by_reason),
            "relations_path": str(self.relations_path),
            "unresolved_path": str(self.unresolved_path),
        }


def _default_workers() -> int:
    configured = os.environ.get("RELATION_BUILDER_WORKERS")
    if configured is not None:
        return int(configured)
    return max(1, (os.cpu_count() or 2) - 1)


def _with_interrupted_retries(
    task: RelationBuildTask,
) -> tuple[DocumentTree, tuple[DocumentGrain, ...]]:
    for attempt in range(INTERRUPTED_RETRIES + 1):
        try:
            tree = compile_document_tree(
                task.directory,
                doc_id=task.doc_id,
                corpus_root=task.corpus_root,
            )
            grains = compile_document_grains(
                tree,
                max_estimated_tokens=task.max_estimated_tokens,
            )
            return tree, grains
        except InterruptedError:
            if attempt == INTERRUPTED_RETRIES:
                raise
            time.sleep(0.05 * (2**attempt))
        except Exception as error:
            raise RuntimeError(f"failed to compile relations for {task.doc_id}: {error}") from error
    raise AssertionError("unreachable interrupted retry state")


def _scan_document(task: RelationBuildTask) -> ScannedRelationDocument:
    try:
        tree = compile_document_tree(
            task.directory,
            doc_id=task.doc_id,
            corpus_root=task.corpus_root,
        )
    except Exception as error:
        raise RuntimeError(f"failed to scan relations for {task.doc_id}: {error}") from error
    return ScannedRelationDocument(
        doc_id=task.doc_id,
        signals=tuple(sorted(str(signal) for signal in tree_relation_signals(tree))),
        linked_receipt_nos=linked_receipt_numbers(tree),
    )


def _cache_document(task: RelationBuildTask) -> CachedRelationDocument:
    if task.cache_directory is None:
        raise ValueError("cache_directory is required for relation cache compilation")
    tree, grains = _with_interrupted_retries(task)
    payload = {
        "tree": tree.model_dump(mode="json"),
        "grains": [grain.model_dump(mode="json") for grain in grains],
    }
    cache_path = task.cache_directory / f"{task.doc_id}.json"
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return CachedRelationDocument(doc_id=task.doc_id, grains=len(grains))


def _run_tasks[Task, Result](
    tasks: Sequence[Task],
    worker: Callable[[Task], Result],
    *,
    workers: int,
) -> Iterator[Result]:
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if workers == 1:
        for task in tasks:
            yield worker(task)
        return

    task_iterator = iter(tasks)
    with ProcessPoolExecutor(max_workers=workers) as executor:
        pending: set[Future[Result]] = {
            executor.submit(worker, task)
            for task in islice(task_iterator, workers * POOL_QUEUE_FACTOR)
        }
        while pending:
            completed, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                result = future.result()
                try:
                    task = next(task_iterator)
                except StopIteration:
                    pass
                else:
                    pending.add(executor.submit(worker, task))
                yield result


def _load_cached_document(
    cache_directory: Path,
    doc_id: str,
) -> tuple[DocumentTree, tuple[DocumentGrain, ...]]:
    value: Any = json.loads((cache_directory / f"{doc_id}.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"invalid relation cache object: {doc_id}")
    grains_value = value.get("grains")
    if not isinstance(grains_value, list):
        raise ValueError(f"invalid relation cache grains: {doc_id}")
    tree = DocumentTree.model_validate(value.get("tree"))
    grains = tuple(DocumentGrain.model_validate(item) for item in grains_value)
    return tree, grains


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _relation_sort_key(relation: DocumentRelation) -> tuple[object, ...]:
    return (
        relation.source_doc_id,
        relation.predicate.value,
        relation.target_doc_id,
        relation.source_grain_ids,
        relation.target_grain_ids,
    )


def _unresolved_sort_key(unresolved: UnresolvedRelation) -> tuple[object, ...]:
    return (
        unresolved.source_doc_id,
        unresolved.predicate.value,
        unresolved.reason.value,
        unresolved.candidate_doc_ids,
    )


def _unresolved_json_value(unresolved: UnresolvedRelation) -> dict[str, object]:
    return {
        "source_doc_id": unresolved.source_doc_id,
        "predicate": unresolved.predicate.value,
        "reason": unresolved.reason.value,
        "candidate_doc_ids": unresolved.candidate_doc_ids,
    }


def _report(
    *,
    documents_scanned: int,
    relation_sources: int,
    documents_compiled_with_grains: int,
    relations: tuple[DocumentRelation, ...],
    unresolved: tuple[UnresolvedRelation, ...],
    output_directory: Path,
) -> RelationBuildReport:
    relations_path = output_directory / "relations.jsonl"
    unresolved_path = output_directory / "unresolved.jsonl"
    _write_jsonl(
        relations_path,
        (relation.model_dump(mode="json") for relation in relations),
    )
    _write_jsonl(
        unresolved_path,
        (_unresolved_json_value(item) for item in unresolved),
    )
    reason_counts = Counter(item.reason.value for item in unresolved)
    return RelationBuildReport(
        documents_scanned=documents_scanned,
        relation_sources=relation_sources,
        documents_compiled_with_grains=documents_compiled_with_grains,
        relations=len(relations),
        unresolved=len(unresolved),
        unresolved_by_reason=dict(sorted(reason_counts.items())),
        relations_path=relations_path,
        unresolved_path=unresolved_path,
    )


def _validate_source_result(
    *,
    source: RelationDocument,
    scan: ScannedRelationDocument,
    linked_targets: tuple[RelationDocument, ...],
    relations: tuple[DocumentRelation, ...],
    unresolved: tuple[UnresolvedRelation, ...],
    grains_by_doc_id: Mapping[str, tuple[DocumentGrain, ...]],
) -> None:
    signals = set(scan.signals) | set(
        manifest_relation_signals(
            {
                "is_correction": source.is_correction,
                "report_name": source.report_name,
                "doc_subtype": source.doc_subtype,
            }
        )
    )
    require_predicate_coverage(signals)
    if RelationSignal.IS_CORRECTION in scan.signals and not source.is_correction:
        raise ValueError(f"tree correction signal disagrees with catalog: {source.doc_id}")

    grains_by_id = {
        grain.grain_id: grain for grains in grains_by_doc_id.values() for grain in grains
    }
    for relation in relations:
        if relation.source_doc_id != source.doc_id:
            raise ValueError(f"resolver emitted a relation for another source: {source.doc_id}")
        validate_relation_grains(relation, grains_by_id=grains_by_id)
    for item in unresolved:
        if item.source_doc_id != source.doc_id:
            raise ValueError(
                f"resolver emitted unresolved state for another source: {source.doc_id}"
            )

    relation_predicates = {relation.predicate for relation in relations}
    unresolved_predicates = {item.predicate for item in unresolved}
    if relation_predicates & unresolved_predicates:
        raise ValueError(f"predicate is both resolved and unresolved: {source.doc_id}")

    if source.is_correction:
        revised = RelationPredicate.REVISES in relation_predicates
        revision_unresolved = RelationPredicate.REVISES in unresolved_predicates
        if revised == revision_unresolved:
            raise ValueError(f"correction must have one REVISES outcome: {source.doc_id}")

    referenced_targets = {
        relation.target_doc_id
        for relation in relations
        if relation.predicate == RelationPredicate.REFERENCES
    }
    expected_targets = {target.doc_id for target in linked_targets}
    if not expected_targets.issubset(referenced_targets):
        missing = sorted(expected_targets - referenced_targets)
        raise ValueError(f"in-corpus receipt links lack REFERENCES edges: {missing}")


def build_relations(
    corpus_root: Path,
    output_directory: Path,
    *,
    workers: int | None = None,
    progress_every: int = 100,
    max_estimated_tokens: int = DEFAULT_MAX_ESTIMATED_TOKENS,
    manual_reviews: ManualRelationReviews | None = None,
) -> RelationBuildReport:
    """Rebuild file-backed relations from manifest, trees, grains, and manual reviews."""

    if workers is None:
        workers = _default_workers()
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if max_estimated_tokens < 1:
        raise ValueError("max_estimated_tokens must be at least 1")

    corpus_root = corpus_root.resolve()
    output_directory = output_directory.resolve()
    manifest_rows = read_documents(corpus_root)
    documents = tuple(RelationDocument.from_mapping(row) for row in manifest_rows)
    catalog = RelationCatalog(documents)
    document_by_id = {document.doc_id: document for document in documents}
    if len(document_by_id) != len(documents):
        raise ValueError("duplicate doc_id in manifest")

    directories = index_document_directories(corpus_root)
    base_tasks: list[RelationBuildTask] = []
    for row in manifest_rows:
        doc_id = str(row["doc_id"])
        file_path = nfc(str(row["file_path"]))
        directory = directories.get(file_path)
        if directory is None:
            raise FileNotFoundError(f"manifest directory not found: {file_path}")
        base_tasks.append(
            RelationBuildTask(
                doc_id=doc_id,
                directory=directory,
                corpus_root=corpus_root,
                max_estimated_tokens=max_estimated_tokens,
            )
        )
    task_by_id = {task.doc_id: task for task in base_tasks}

    scans: dict[str, ScannedRelationDocument] = {}
    for position, scan in enumerate(
        _run_tasks(base_tasks, _scan_document, workers=workers),
        start=1,
    ):
        scans[scan.doc_id] = scan
        if progress_every > 0 and position % progress_every == 0:
            print(f"scanned {position}/{len(base_tasks)} documents for relations", flush=True)
    if set(scans) != set(document_by_id):
        raise RuntimeError("relation scan did not cover every manifest document")

    linked_targets_by_source: dict[str, tuple[RelationDocument, ...]] = {}
    source_ids: set[str] = set()
    for document in documents:
        linked_targets = tuple(
            target
            for receipt_no in scans[document.doc_id].linked_receipt_nos
            if (target := catalog.by_linked_receipt_no(receipt_no)) is not None
            and target.doc_id != document.doc_id
        )
        linked_targets_by_source[document.doc_id] = linked_targets
        if document.is_correction or linked_targets:
            source_ids.add(document.doc_id)

    series: dict[tuple[object, ...], list[RelationDocument]] = defaultdict(list)
    for document in documents:
        series[relation_series_key(document)].append(document)

    required_ids = set(source_ids)
    for source_id in source_ids:
        source = document_by_id[source_id]
        required_ids.update(target.doc_id for target in linked_targets_by_source[source_id])
        if source.is_correction:
            required_ids.update(
                candidate.doc_id
                for candidate in series[relation_series_key(source)]
                if candidate.receipt_no < source.receipt_no
            )

    relations: list[DocumentRelation] = []
    unresolved: list[UnresolvedRelation] = []
    with tempfile.TemporaryDirectory(prefix="disclosure-relations-") as cache_name:
        cache_directory = Path(cache_name)
        cache_tasks = tuple(
            RelationBuildTask(
                doc_id=task_by_id[doc_id].doc_id,
                directory=task_by_id[doc_id].directory,
                corpus_root=corpus_root,
                max_estimated_tokens=max_estimated_tokens,
                cache_directory=cache_directory,
            )
            for doc_id in sorted(required_ids)
        )
        for position, _ in enumerate(
            _run_tasks(cache_tasks, _cache_document, workers=workers),
            start=1,
        ):
            if progress_every > 0 and position % progress_every == 0:
                print(
                    f"compiled {position}/{len(cache_tasks)} relation documents",
                    flush=True,
                )

        resolver = DocumentRelationResolver(manual_reviews=manual_reviews)
        ordered_source_ids = tuple(sorted(source_ids))
        for position, source_id in enumerate(ordered_source_ids, start=1):
            source = document_by_id[source_id]
            source_tree, source_grains = _load_cached_document(cache_directory, source_id)
            context_ids = {source_id}
            context_ids.update(target.doc_id for target in linked_targets_by_source[source_id])
            if source.is_correction:
                context_ids.update(
                    candidate.doc_id
                    for candidate in series[relation_series_key(source)]
                    if candidate.receipt_no < source.receipt_no
                )
            grains_by_doc_id = {
                doc_id: _load_cached_document(cache_directory, doc_id)[1]
                for doc_id in sorted(context_ids)
            }
            result = resolver.resolve_detailed(
                RelationResolutionContext(
                    source_document=source,
                    source_tree=source_tree,
                    source_grains=source_grains,
                    catalog=catalog,
                    grains_by_doc_id=grains_by_doc_id,
                )
            )
            _validate_source_result(
                source=source,
                scan=scans[source_id],
                linked_targets=linked_targets_by_source[source_id],
                relations=result.relations,
                unresolved=result.unresolved,
                grains_by_doc_id=grains_by_doc_id,
            )
            relations.extend(result.relations)
            unresolved.extend(result.unresolved)
            if progress_every > 0 and position % progress_every == 0:
                print(
                    f"resolved {position}/{len(ordered_source_ids)} relation sources",
                    flush=True,
                )

    unique_relations = tuple(dict.fromkeys(relations))
    unique_unresolved = tuple(dict.fromkeys(unresolved))
    if len(unique_relations) != len(relations):
        raise ValueError("relation build emitted duplicate edges")
    if len(unique_unresolved) != len(unresolved):
        raise ValueError("relation build emitted duplicate unresolved states")

    ordered_relations = tuple(sorted(unique_relations, key=_relation_sort_key))
    ordered_unresolved = tuple(sorted(unique_unresolved, key=_unresolved_sort_key))
    return _report(
        documents_scanned=len(scans),
        relation_sources=len(source_ids),
        documents_compiled_with_grains=len(required_ids),
        relations=ordered_relations,
        unresolved=ordered_unresolved,
        output_directory=output_directory,
    )


def _database_tree(
    cursor: psycopg.Cursor[dict[str, Any]],
    doc_id: str,
) -> DocumentTree:
    cursor.execute(
        "SELECT tree FROM corpus.document_tree WHERE doc_id = %s",
        (doc_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError(f"document_tree row is missing: {doc_id}")
    return DocumentTree.model_validate(row["tree"])


def _database_grains(
    cursor: psycopg.Cursor[dict[str, Any]],
    doc_id: str,
    grain_ids: Sequence[str] | None = None,
) -> tuple[DocumentGrain, ...]:
    where = "WHERE doc_id = %s"
    parameters: tuple[object, ...] = (doc_id,)
    if grain_ids is not None:
        if not grain_ids:
            return ()
        where += " AND grain_id = ANY(%s)"
        parameters = (doc_id, list(grain_ids))
    cursor.execute(
        f"""
        SELECT
            schema_version,
            compiler_version,
            grain_id,
            doc_id,
            kind,
            core_text,
            rendered_text,
            estimated_tokens,
            semantic_context AS context,
            source_address AS source,
            previous_grain_id,
            next_grain_id
        FROM corpus.document_grain
        {where}
        ORDER BY ordinal
        """,
        parameters,
    )
    grains = tuple(DocumentGrain.model_validate(row) for row in cursor.fetchall())
    if grain_ids is None and not grains:
        raise RuntimeError(f"document_grain rows are missing: {doc_id}")
    return grains


_RECEIPT_PARAMETER = re.compile(r"(rcpno|acptno)=([0-9]{14})", re.IGNORECASE)
_LINKED_NODE_JSONPATH = (
    '$.** ? (exists(@.attributes[*] ? (@.value like_regex "(rcpno|acptno)=[0-9]{14}" flag "i")))'
)


def _linked_receipt_from_node_value(value: object) -> LinkedReceiptAnchor | None:
    if not isinstance(value, dict):
        return None
    parameters = {
        name.lower(): receipt_no
        for attribute in value.get("attributes", ())
        if isinstance(attribute, dict)
        for name, receipt_no in _RECEIPT_PARAMETER.findall(str(attribute.get("value", "")))
    }
    receipt_no = parameters.get("rcpno") or parameters.get("acptno")
    if receipt_no is None:
        return None
    return LinkedReceiptAnchor(
        receipt_no=receipt_no,
        source=SourceRange.model_validate(value.get("source")),
    )


def _linked_receipts_from_tree_value(value: object) -> tuple[LinkedReceiptAnchor, ...]:
    if not isinstance(value, dict) or not isinstance(value.get("artifacts"), list):
        raise ValueError("invalid document tree JSONB")
    stack = [
        artifact.get("root")
        for artifact in value["artifacts"]
        if isinstance(artifact, dict) and isinstance(artifact.get("root"), dict)
    ]
    anchors: list[LinkedReceiptAnchor] = []
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        anchor = _linked_receipt_from_node_value(node)
        if anchor is not None:
            anchors.append(anchor)
        content = node.get("content")
        if isinstance(content, list):
            stack.extend(item for item in reversed(content) if isinstance(item, dict))
    return tuple(anchors)


def _database_all_linked_receipts(
    cursor: psycopg.Cursor[dict[str, Any]],
    doc_ids: Sequence[str],
    *,
    batch_size: int = 1,
    progress_every: int = 100,
) -> dict[str, tuple[LinkedReceiptAnchor, ...]]:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    grouped: dict[str, tuple[LinkedReceiptAnchor, ...]] = {}
    for start in range(0, len(doc_ids), batch_size):
        batch = list(doc_ids[start : start + batch_size])
        cursor.execute(
            """
            SELECT tree.doc_id, linked.node
            FROM corpus.document_tree AS tree
            CROSS JOIN LATERAL jsonb_path_query(
                tree.tree,
                %s::jsonpath
            ) AS linked(node)
            WHERE tree.doc_id = ANY(%s)
            ORDER BY tree.doc_id
            """,
            (_LINKED_NODE_JSONPATH, batch),
        )
        for row in cursor.fetchall():
            anchor = _linked_receipt_from_node_value(row["node"])
            if anchor is not None:
                doc_id = str(row["doc_id"])
                grouped[doc_id] = (*grouped.get(doc_id, ()), anchor)
        completed = min(start + batch_size, len(doc_ids))
        if progress_every > 0 and (
            completed == len(doc_ids) or completed // progress_every != start // progress_every
        ):
            print(
                f"scanned {completed}/{len(doc_ids)} DB document trees",
                flush=True,
            )
    return grouped


def _database_filing_dates(
    cursor: psycopg.Cursor[dict[str, Any]],
    doc_id: str,
) -> tuple[str, ...]:
    cursor.execute(
        """
        SELECT core_text
        FROM corpus.document_grain
        WHERE doc_id = %s
          AND (
              core_text LIKE '%%최초제출일%%'
              OR core_text LIKE '%%공시서류제출일%%'
              OR core_text LIKE '%%최초보고일%%'
          )
        ORDER BY ordinal
        """,
        (doc_id,),
    )
    return original_filing_dates(" ".join(str(row["core_text"]) for row in cursor.fetchall()))


def _raw_ranges_overlap(left: SourceRange, right: SourceRange) -> bool:
    return (
        left.artifact_id == right.artifact_id
        and left.source_path == right.source_path
        and left.start_byte < right.end_byte
        and right.start_byte < left.end_byte
    )


def _database_evidence_grains(
    cursor: psycopg.Cursor[dict[str, Any]],
    doc_id: str,
    linked_receipts: Sequence[LinkedReceiptAnchor],
) -> tuple[tuple[DocumentGrain, ...], tuple[str, ...]]:
    cursor.execute(
        """
        SELECT grain_id, core_text, source_address AS source
        FROM corpus.document_grain
        WHERE doc_id = %s
        ORDER BY ordinal
        """,
        (doc_id,),
    )
    selected_ids: list[str] = []
    correction_ids: list[str] = []
    linked_ranges = tuple(item.source for item in linked_receipts)
    for row in cursor.fetchall():
        address = SourceAddress.model_validate(row["source"])
        core_text = str(row["core_text"])
        is_correction_evidence = has_correction_marker(core_text)
        is_link_evidence = any(
            _raw_ranges_overlap(linked_range, core_range)
            for linked_range in linked_ranges
            for core_range in address.core_ranges
        )
        if is_correction_evidence or is_link_evidence:
            selected_ids.append(str(row["grain_id"]))
        if is_correction_evidence:
            correction_ids.append(str(row["grain_id"]))
    return (
        _database_grains(cursor, doc_id, selected_ids),
        tuple(correction_ids),
    )


def build_relations_from_database(
    database_url: str,
    output_directory: Path,
    *,
    progress_every: int = 100,
    manual_reviews: ManualRelationReviews | None = None,
) -> RelationBuildReport:
    """Build a file-backed relation snapshot from the exact DB tree/grain snapshot."""

    output_directory = output_directory.resolve()
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL temp_file_limit = '512MB'")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    doc_id,
                    receipt_no,
                    corp_code,
                    doc_group,
                    doc_subtype,
                    report_name,
                    is_correction,
                    filer_name,
                    base_year,
                    base_month
                FROM corpus.disclosure_document
                ORDER BY receipt_no
                """
            )
            documents = tuple(RelationDocument.from_mapping(row) for row in cursor.fetchall())
            catalog = RelationCatalog(documents)
            document_by_id = {document.doc_id: document for document in documents}

            linked_receipts_by_doc_id = _database_all_linked_receipts(
                cursor,
                tuple(document_by_id),
                progress_every=progress_every,
            )
            source_ids = tuple(
                sorted(
                    document.doc_id
                    for document in documents
                    if document.is_correction or document.doc_id in linked_receipts_by_doc_id
                )
            )

            series: dict[tuple[object, ...], list[RelationDocument]] = defaultdict(list)
            for document in documents:
                series[relation_series_key(document)].append(document)

            resolver = DocumentRelationResolver(manual_reviews=manual_reviews)
            relations: list[DocumentRelation] = []
            unresolved: list[UnresolvedRelation] = []
            for position, source_id in enumerate(source_ids, start=1):
                source = document_by_id[source_id]
                linked_receipts = linked_receipts_by_doc_id.get(source_id, ())
                source_grains, correction_grain_ids = _database_evidence_grains(
                    cursor,
                    source_id,
                    linked_receipts,
                )
                source_filing_dates = _database_filing_dates(cursor, source_id)
                scan = ScannedRelationDocument(
                    doc_id=source_id,
                    signals=tuple(
                        signal
                        for signal, present in (
                            (RelationSignal.IS_CORRECTION.value, source.is_correction),
                            (RelationSignal.RELATED_DISCLOSURE.value, bool(linked_receipts)),
                        )
                        if present
                    ),
                    linked_receipt_nos=tuple(
                        dict.fromkeys(item.receipt_no for item in linked_receipts)
                    ),
                )
                linked_targets = tuple(
                    target
                    for receipt_no in scan.linked_receipt_nos
                    if (target := catalog.by_linked_receipt_no(receipt_no)) is not None
                    and target.doc_id != source_id
                )
                has_explicit_revision = any(
                    target.receipt_no < source.receipt_no
                    and relation_series_key(target) == relation_series_key(source)
                    for target in linked_targets
                )
                filing_dates_by_doc_id = {source_id: source_filing_dates}
                if source.is_correction and not has_explicit_revision:
                    for candidate in series[relation_series_key(source)]:
                        if candidate.receipt_no >= source.receipt_no or not candidate.is_correction:
                            continue
                        filing_dates_by_doc_id[candidate.doc_id] = _database_filing_dates(
                            cursor,
                            candidate.doc_id,
                        )

                grains_by_doc_id = {source_id: source_grains}
                result = resolver.resolve_detailed(
                    RelationResolutionContext(
                        source_document=source,
                        source_tree=None,
                        source_grains=source_grains,
                        catalog=catalog,
                        grains_by_doc_id=grains_by_doc_id,
                        linked_receipts=linked_receipts,
                        filing_dates_by_doc_id=filing_dates_by_doc_id,
                        correction_grain_ids=correction_grain_ids,
                    )
                )
                _validate_source_result(
                    source=source,
                    scan=scan,
                    linked_targets=linked_targets,
                    relations=result.relations,
                    unresolved=result.unresolved,
                    grains_by_doc_id=grains_by_doc_id,
                )
                relations.extend(result.relations)
                unresolved.extend(result.unresolved)
                if progress_every > 0 and position % progress_every == 0:
                    print(
                        f"resolved {position}/{len(source_ids)} DB relation sources",
                        flush=True,
                    )

    unique_relations = tuple(dict.fromkeys(relations))
    unique_unresolved = tuple(dict.fromkeys(unresolved))
    if len(unique_relations) != len(relations):
        raise ValueError("relation build emitted duplicate edges")
    if len(unique_unresolved) != len(unresolved):
        raise ValueError("relation build emitted duplicate unresolved states")
    return _report(
        documents_scanned=len(documents),
        relation_sources=len(source_ids),
        documents_compiled_with_grains=len(source_ids),
        relations=tuple(sorted(unique_relations, key=_relation_sort_key)),
        unresolved=tuple(sorted(unique_unresolved, key=_unresolved_sort_key)),
        output_directory=output_directory,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild file-backed document relations without writing to the database."
    )
    parser.add_argument("--corpus-root", type=Path, default=PROJECT_ROOT / "corpus")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "relations",
    )
    parser.add_argument("--workers", type=int, default=_default_workers())
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument(
        "--max-estimated-tokens",
        type=int,
        default=DEFAULT_MAX_ESTIMATED_TOKENS,
    )
    parser.add_argument("--manual-reviews", type=Path)
    parser.add_argument(
        "--from-database",
        action="store_true",
        help="Read the current JSONB document trees and grains from the database.",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    arguments = parser.parse_args()
    reviews = (
        ManualRelationReviews.from_jsonl(arguments.manual_reviews)
        if arguments.manual_reviews is not None
        else None
    )
    if arguments.from_database:
        report = build_relations_from_database(
            arguments.database_url,
            arguments.output_dir,
            progress_every=arguments.progress_every,
            manual_reviews=reviews,
        )
    else:
        report = build_relations(
            arguments.corpus_root,
            arguments.output_dir,
            workers=arguments.workers,
            progress_every=arguments.progress_every,
            max_estimated_tokens=arguments.max_estimated_tokens,
            manual_reviews=reviews,
        )
    print(json.dumps(report.as_json_value(), ensure_ascii=False))
    ambiguous = report.unresolved_by_reason.get("ambiguous_candidates", 0)
    if ambiguous:
        parser.exit(
            status=2,
            message=(
                f"relation snapshot contains {ambiguous} unreviewed ambiguous "
                f"correction(s); inspect {report.unresolved_path}\n"
            ),
        )


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import sys
import time
import unicodedata
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from evidence.compiler import compile_document_tree
from evidence.document_tree import DocumentTree, Node, SourceRange, Text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TREE_SUFFIXES = {".xml", ".html"}


def _default_workers() -> int:
    configured = os.environ.get("CORPUS_VALIDATION_WORKERS")
    if configured is not None:
        return int(configured)
    return max(1, (os.cpu_count() or 2) - 1)


@dataclass(frozen=True)
class ManifestDocument:
    doc_id: str
    file_path: str
    file_count: int


@dataclass(frozen=True)
class ValidationTask:
    position: int
    document: ManifestDocument
    directory: Path
    corpus_root: Path


@dataclass(frozen=True)
class DocumentValidationResult:
    position: int
    source_artifacts: int = 0
    expected_tree_artifacts: int = 0
    compiled_tree_artifacts: int = 0
    validated_nodes: int = 0
    validated_texts: int = 0
    failure: ValidationFailure | None = None


class ValidationFailure(BaseModel):
    model_config = ConfigDict(frozen=True)

    doc_id: str | None
    file_path: str | None
    error_type: str
    message: str


class CorpusValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    passed: bool
    manifest_documents: int = Field(ge=0)
    filesystem_documents: int = Field(ge=0)
    source_artifacts: int = Field(ge=0)
    expected_tree_artifacts: int = Field(ge=0)
    compiled_tree_artifacts: int = Field(ge=0)
    validated_nodes: int = Field(ge=0)
    validated_texts: int = Field(ge=0)
    elapsed_seconds: float = Field(ge=0)
    failures: tuple[ValidationFailure, ...] = ()


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _read_manifest(corpus_root: Path) -> list[ManifestDocument]:
    documents: list[ManifestDocument] = []
    with (corpus_root / "manifest.jsonl").open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                row = json.loads(line)
                documents.append(
                    ManifestDocument(
                        doc_id=str(row["doc_id"]),
                        file_path=str(row["file_path"]),
                        file_count=int(row["n_files"]),
                    )
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise ValueError(f"invalid manifest row {line_number}: {error}") from error
    return documents


def _index_document_directories(corpus_root: Path) -> dict[str, Path]:
    raw_root = corpus_root / "raw"
    result: dict[str, Path] = {}
    for group in raw_root.iterdir():
        if not group.is_dir():
            continue
        for company in group.iterdir():
            if not company.is_dir():
                continue
            for directory in company.iterdir():
                if not directory.is_dir():
                    continue
                relative_path = directory.relative_to(corpus_root).as_posix()
                normalized_path = _nfc(relative_path)
                if normalized_path in result:
                    raise ValueError(f"duplicate NFC document path: {normalized_path}")
                result[normalized_path] = directory
    return result


def _source_files(directory: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            path for path in directory.iterdir() if path.is_file() and not path.name.startswith(".")
        )
    )


def _tree_files(files: tuple[Path, ...]) -> tuple[Path, ...]:
    return tuple(path for path in files if path.suffix.lower() in TREE_SUFFIXES)


def _validate_range(
    source: SourceRange, artifact_id: str, source_path: str, byte_size: int
) -> None:
    if source.artifact_id != artifact_id:
        raise ValueError(f"source artifact mismatch at {source.xpath}")
    if source.source_path != source_path:
        raise ValueError(f"source path mismatch at {source.xpath}")
    if source.end_byte > byte_size:
        raise ValueError(f"source range exceeds artifact bytes at {source.xpath}")


def _validate_text(
    text: Text,
    *,
    artifact_id: str,
    source_path: str,
    source_bytes: bytes,
) -> None:
    _validate_range(text.source, artifact_id, source_path, len(source_bytes))
    source_slice = source_bytes[text.source.start_byte : text.source.end_byte].decode("utf-8")
    if source_slice != text.raw_value:
        raise ValueError(f"raw text does not match source bytes at {text.source.xpath}")
    expected_display = " ".join(html.unescape(text.raw_value).strip().split())
    if expected_display != text.display_value:
        raise ValueError(f"display text does not match raw text at {text.source.xpath}")


def _validate_node(
    node: Node,
    *,
    artifact_id: str,
    source_path: str,
    source_bytes: bytes,
) -> tuple[int, int]:
    _validate_range(node.source, artifact_id, source_path, len(source_bytes))
    node_count = 1
    text_count = 0
    for item in node.content:
        if isinstance(item, Text):
            _validate_text(
                item,
                artifact_id=artifact_id,
                source_path=source_path,
                source_bytes=source_bytes,
            )
            text_count += 1
        else:
            child_nodes, child_texts = _validate_node(
                item,
                artifact_id=artifact_id,
                source_path=source_path,
                source_bytes=source_bytes,
            )
            node_count += child_nodes
            text_count += child_texts
    return node_count, text_count


def _validate_tree(
    tree: DocumentTree,
    *,
    corpus_root: Path,
    expected_files: tuple[Path, ...],
) -> tuple[int, int]:
    expected_paths = {path.relative_to(corpus_root).as_posix() for path in expected_files}
    actual_paths = {artifact.source_path for artifact in tree.artifacts}
    if actual_paths != expected_paths:
        missing = sorted(expected_paths - actual_paths)
        unexpected = sorted(actual_paths - expected_paths)
        raise ValueError(f"artifact coverage mismatch: missing={missing} unexpected={unexpected}")

    restored = DocumentTree.model_validate_json(tree.model_dump_json())
    if restored != tree:
        raise ValueError("DocumentTree JSON round-trip changed the tree")

    node_count = 0
    text_count = 0
    for artifact in tree.artifacts:
        source_file = corpus_root / artifact.source_path
        source_bytes = source_file.read_bytes()
        if artifact.byte_size != len(source_bytes):
            raise ValueError(f"byte size mismatch: {artifact.source_path}")
        if artifact.source_sha256 != hashlib.sha256(source_bytes).hexdigest():
            raise ValueError(f"SHA-256 mismatch: {artifact.source_path}")
        if artifact.title is not None:
            _validate_range(
                artifact.title.source,
                artifact.artifact_id,
                artifact.source_path,
                len(source_bytes),
            )
        artifact_nodes, artifact_texts = _validate_node(
            artifact.root,
            artifact_id=artifact.artifact_id,
            source_path=artifact.source_path,
            source_bytes=source_bytes,
        )
        node_count += artifact_nodes
        text_count += artifact_texts
    return node_count, text_count


def _validate_document(task: ValidationTask) -> DocumentValidationResult:
    document = task.document
    source_artifacts = 0
    expected_tree_artifacts = 0
    try:
        files = _source_files(task.directory)
        source_artifacts = len(files)
        if len(files) != document.file_count:
            raise ValueError(
                f"file count mismatch: manifest={document.file_count} actual={len(files)}"
            )
        tree_files = _tree_files(files)
        expected_tree_artifacts = len(tree_files)
        if not tree_files:
            raise ValueError("document has no XML or HTML artifact")

        tree = compile_document_tree(
            task.directory,
            doc_id=document.doc_id,
            corpus_root=task.corpus_root,
        )
        if tree.doc_id != document.doc_id:
            raise ValueError(f"tree doc_id mismatch: {tree.doc_id}")
        document_nodes, document_texts = _validate_tree(
            tree,
            corpus_root=task.corpus_root,
            expected_files=tree_files,
        )
        return DocumentValidationResult(
            position=task.position,
            source_artifacts=source_artifacts,
            expected_tree_artifacts=expected_tree_artifacts,
            compiled_tree_artifacts=len(tree.artifacts),
            validated_nodes=document_nodes,
            validated_texts=document_texts,
        )
    except Exception as error:  # A worker returns errors so the parent can report the full corpus.
        return DocumentValidationResult(
            position=task.position,
            source_artifacts=source_artifacts,
            expected_tree_artifacts=expected_tree_artifacts,
            failure=ValidationFailure(
                doc_id=document.doc_id,
                file_path=document.file_path,
                error_type=type(error).__name__,
                message=str(error),
            ),
        )


def validate_corpus(
    corpus_root: Path,
    *,
    progress_every: int = 100,
    fail_fast: bool = False,
    workers: int = 1,
) -> CorpusValidationReport:
    started_at = time.monotonic()
    corpus_root = corpus_root.resolve()
    documents = _read_manifest(corpus_root)
    directories = _index_document_directories(corpus_root)
    failures: list[ValidationFailure] = []

    manifest_paths = [_nfc(document.file_path) for document in documents]
    duplicate_doc_ids = sorted(
        doc_id
        for doc_id in {document.doc_id for document in documents}
        if sum(document.doc_id == doc_id for document in documents) > 1
    )
    duplicate_paths = sorted(path for path in set(manifest_paths) if manifest_paths.count(path) > 1)
    if duplicate_doc_ids:
        failures.append(
            ValidationFailure(
                doc_id=None,
                file_path=None,
                error_type="DuplicateManifestDocument",
                message=f"duplicate doc_id values: {duplicate_doc_ids}",
            )
        )
    if duplicate_paths:
        failures.append(
            ValidationFailure(
                doc_id=None,
                file_path=None,
                error_type="DuplicateManifestPath",
                message=f"duplicate file_path values: {duplicate_paths}",
            )
        )

    manifest_path_set = set(manifest_paths)
    filesystem_path_set = set(directories)
    missing_directories = sorted(manifest_path_set - filesystem_path_set)
    unlisted_directories = sorted(filesystem_path_set - manifest_path_set)
    if missing_directories:
        failures.append(
            ValidationFailure(
                doc_id=None,
                file_path=None,
                error_type="MissingDocumentDirectory",
                message=f"manifest paths missing from raw/: {missing_directories}",
            )
        )
    if unlisted_directories:
        failures.append(
            ValidationFailure(
                doc_id=None,
                file_path=None,
                error_type="UnlistedDocumentDirectory",
                message=f"raw/ paths missing from manifest: {unlisted_directories}",
            )
        )

    source_artifacts = 0
    expected_tree_artifacts = 0
    compiled_tree_artifacts = 0
    validated_nodes = 0
    validated_texts = 0

    if workers < 1:
        raise ValueError("workers must be at least 1")
    tasks = tuple(
        ValidationTask(
            position=position,
            document=document,
            directory=directory,
            corpus_root=corpus_root,
        )
        for position, document in enumerate(documents, start=1)
        if (directory := directories.get(_nfc(document.file_path))) is not None
    )

    def collect(result: DocumentValidationResult) -> bool:
        nonlocal source_artifacts
        nonlocal expected_tree_artifacts
        nonlocal compiled_tree_artifacts
        nonlocal validated_nodes
        nonlocal validated_texts
        source_artifacts += result.source_artifacts
        expected_tree_artifacts += result.expected_tree_artifacts
        compiled_tree_artifacts += result.compiled_tree_artifacts
        validated_nodes += result.validated_nodes
        validated_texts += result.validated_texts
        if result.failure is not None:
            failures.append(result.failure)
            if fail_fast:
                return False
        if progress_every > 0 and result.position % progress_every == 0:
            print(
                f"checked {result.position}/{len(documents)} documents; failures={len(failures)}",
                file=sys.stderr,
                flush=True,
            )
        return True

    if workers == 1:
        for task in tasks:
            if not collect(_validate_document(task)):
                break
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            for result in executor.map(_validate_document, tasks, chunksize=1):
                if not collect(result):
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

    return CorpusValidationReport(
        passed=not failures,
        manifest_documents=len(documents),
        filesystem_documents=len(directories),
        source_artifacts=source_artifacts,
        expected_tree_artifacts=expected_tree_artifacts,
        compiled_tree_artifacts=compiled_tree_artifacts,
        validated_nodes=validated_nodes,
        validated_texts=validated_texts,
        elapsed_seconds=round(time.monotonic() - started_at, 3),
        failures=tuple(failures),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile and validate DocumentTree coverage for the whole raw corpus."
    )
    parser.add_argument("--corpus-root", type=Path, default=PROJECT_ROOT / "corpus")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument(
        "--workers",
        type=int,
        default=_default_workers(),
        help="Document processes to run in parallel (default: CPU count minus one).",
    )
    arguments = parser.parse_args()

    report = validate_corpus(
        arguments.corpus_root,
        progress_every=arguments.progress_every,
        fail_fast=arguments.fail_fast,
        workers=arguments.workers,
    )
    report_json = report.model_dump_json(indent=2)
    if arguments.report is not None:
        arguments.report.write_text(f"{report_json}\n", encoding="utf-8")
    print(report_json)
    raise SystemExit(0 if report.passed else 1)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Iterator, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any

import psycopg

from evidence.compiler import compile_document_tree
from evidence.document_grain import DocumentGrain
from evidence.grain_compiler import DEFAULT_MAX_ESTIMATED_TOKENS, compile_document_grains
from evidence.loader import (
    DEFAULT_DATABASE_URL,
    index_document_directories,
    nfc,
    read_documents,
    read_sql,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
POOL_QUEUE_FACTOR = 2
INTERRUPTED_RETRIES = 5


@dataclass(frozen=True)
class CompileGrainsTask:
    doc_id: str
    directory: Path
    corpus_root: Path
    max_estimated_tokens: int


@dataclass(frozen=True)
class CompiledDocumentGrains:
    doc_id: str
    rows: tuple[dict[str, Any], ...]


def _default_workers() -> int:
    configured = os.environ.get("DOCUMENT_GRAIN_LOADER_WORKERS")
    if configured is not None:
        return int(configured)
    return max(1, (os.cpu_count() or 2) - 1)


def _grain_row(grain: DocumentGrain) -> dict[str, Any]:
    return {
        "grain_id": grain.grain_id,
        "doc_id": grain.doc_id,
        "artifact_id": grain.source.artifact_id,
        "ordinal": grain.source.ordinal,
        "kind": str(grain.kind),
        "schema_version": grain.schema_version,
        "compiler_version": grain.compiler_version,
        "core_text": grain.core_text,
        "rendered_text": grain.rendered_text,
        "estimated_tokens": grain.estimated_tokens,
        "semantic_context_json": grain.context.model_dump_json(),
        "source_address_json": grain.source.model_dump_json(),
        "previous_grain_id": grain.previous_grain_id,
        "next_grain_id": grain.next_grain_id,
    }


def _compile_document(task: CompileGrainsTask) -> CompiledDocumentGrains:
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
            return CompiledDocumentGrains(
                doc_id=task.doc_id,
                rows=tuple(_grain_row(grain) for grain in grains),
            )
        except InterruptedError:
            if attempt == INTERRUPTED_RETRIES:
                raise
            time.sleep(0.05 * (2**attempt))
        except Exception as error:
            raise RuntimeError(f"failed to compile grains for {task.doc_id}: {error}") from error
    raise AssertionError("unreachable interrupted retry state")


def _compile_documents(
    tasks: Sequence[CompileGrainsTask], workers: int
) -> Iterator[CompiledDocumentGrains]:
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if workers == 1:
        for task in tasks:
            yield _compile_document(task)
        return

    task_iterator = iter(tasks)
    with ProcessPoolExecutor(max_workers=workers) as executor:
        pending: set[Future[CompiledDocumentGrains]] = {
            executor.submit(_compile_document, task)
            for task in islice(task_iterator, workers * POOL_QUEUE_FACTOR)
        }
        while pending:
            completed, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                compiled = future.result()
                try:
                    task = next(task_iterator)
                except StopIteration:
                    pass
                else:
                    pending.add(executor.submit(_compile_document, task))
                yield compiled


def _batches(
    documents: Iterator[CompiledDocumentGrains], batch_size: int
) -> Iterator[list[CompiledDocumentGrains]]:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    while batch := list(islice(documents, batch_size)):
        yield batch


def _tasks(corpus_root: Path, max_estimated_tokens: int) -> tuple[CompileGrainsTask, ...]:
    documents = read_documents(corpus_root)
    directories = index_document_directories(corpus_root)
    result: list[CompileGrainsTask] = []
    for document in documents:
        file_path = nfc(str(document["file_path"]))
        directory = directories.get(file_path)
        if directory is None:
            raise FileNotFoundError(f"manifest directory not found: {file_path}")
        result.append(
            CompileGrainsTask(
                doc_id=str(document["doc_id"]),
                directory=directory,
                corpus_root=corpus_root,
                max_estimated_tokens=max_estimated_tokens,
            )
        )
    return tuple(result)


def load_document_grains(
    database_url: str,
    corpus_root: Path,
    *,
    workers: int | None = None,
    document_batch_size: int = 10,
    progress_every: int = 100,
    max_estimated_tokens: int = DEFAULT_MAX_ESTIMATED_TOKENS,
) -> tuple[int, int]:
    if workers is None:
        workers = _default_workers()
    if max_estimated_tokens < 1:
        raise ValueError("max_estimated_tokens must be at least 1")

    corpus_root = corpus_root.resolve()
    tasks = _tasks(corpus_root, max_estimated_tokens)
    create_table_sql = read_sql("009_create_document_grain.sql")
    upsert_grain_sql = read_sql("010_upsert_document_grain.sql")
    loaded_documents = 0
    loaded_grains = 0
    with psycopg.connect(database_url) as connection:
        connection.execute(create_table_sql)
        connection.commit()
        with connection.cursor() as cursor:
            compiled_documents = _compile_documents(tasks, workers)
            for batch in _batches(compiled_documents, document_batch_size):
                doc_ids = [document.doc_id for document in batch]
                cursor.execute(
                    "DELETE FROM corpus.document_grain WHERE doc_id = ANY(%s::text[])",
                    (doc_ids,),
                )
                rows = [row for document in batch for row in document.rows]
                cursor.executemany(upsert_grain_sql, rows)
                connection.commit()
                loaded_documents += len(batch)
                loaded_grains += len(rows)
                if progress_every > 0 and loaded_documents % progress_every == 0:
                    print(
                        f"loaded {loaded_documents}/{len(tasks)} documents; grains={loaded_grains}",
                        flush=True,
                    )

            cursor.execute(
                """
                SELECT source.doc_id
                FROM unnest(%s::text[]) AS source(doc_id)
                LEFT JOIN (
                    SELECT DISTINCT doc_id FROM corpus.document_grain
                ) AS grain USING (doc_id)
                WHERE grain.doc_id IS NULL
                LIMIT 20
                """,
                ([task.doc_id for task in tasks],),
            )
            missing = [str(row[0]) for row in cursor.fetchall()]
            if missing:
                raise RuntimeError(f"document grain rows missing after load: {missing}")
    return loaded_documents, loaded_grains


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile semantic document grains and upsert compact runtime rows."
    )
    parser.add_argument("--corpus-root", type=Path, default=PROJECT_ROOT / "corpus")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=_default_workers(),
        help="Compiler processes to run in parallel (default: CPU count minus one).",
    )
    parser.add_argument("--document-batch-size", type=int, default=10)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument(
        "--max-estimated-tokens",
        type=int,
        default=DEFAULT_MAX_ESTIMATED_TOKENS,
        help="Conservative dependency-free token budget for rendered grain text.",
    )
    arguments = parser.parse_args()

    documents, grains = load_document_grains(
        arguments.database_url,
        arguments.corpus_root,
        workers=arguments.workers,
        document_batch_size=arguments.document_batch_size,
        progress_every=arguments.progress_every,
        max_estimated_tokens=arguments.max_estimated_tokens,
    )
    print(json.dumps({"documents": documents, "grains": grains}))


if __name__ == "__main__":
    main()

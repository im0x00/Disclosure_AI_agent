from __future__ import annotations

import argparse
import json
import os
import unicodedata
from collections.abc import Iterator, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import dataclass
from itertools import islice
from pathlib import Path

import psycopg

from evidence.compiler import compile_document_tree
from evidence.loader import DEFAULT_DATABASE_URL, read_sql

PROJECT_ROOT = Path(__file__).resolve().parents[2]
POOL_QUEUE_FACTOR = 2


def _default_workers() -> int:
    configured = os.environ.get("DOCUMENT_TREE_LOADER_WORKERS")
    if configured is not None:
        return int(configured)
    return max(1, (os.cpu_count() or 2) - 1)


@dataclass(frozen=True)
class LoadDocument:
    doc_id: str
    file_path: str


@dataclass(frozen=True)
class CompileTask:
    document: LoadDocument
    directory: Path
    corpus_root: Path


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _read_documents(corpus_root: Path) -> tuple[LoadDocument, ...]:
    documents: list[LoadDocument] = []
    with (corpus_root / "manifest.jsonl").open(encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            documents.append(
                LoadDocument(doc_id=str(row["doc_id"]), file_path=str(row["file_path"]))
            )
    return tuple(documents)


def _index_document_directories(corpus_root: Path) -> dict[str, Path]:
    directories: dict[str, Path] = {}
    for group in (corpus_root / "raw").iterdir():
        if not group.is_dir():
            continue
        for company in group.iterdir():
            if not company.is_dir():
                continue
            for directory in company.iterdir():
                if directory.is_dir():
                    path = _nfc(directory.relative_to(corpus_root).as_posix())
                    if path in directories:
                        raise ValueError(f"duplicate NFC document path: {path}")
                    directories[path] = directory
    return directories


def _compile_row(task: CompileTask) -> dict[str, str]:
    try:
        tree = compile_document_tree(
            task.directory,
            doc_id=task.document.doc_id,
            corpus_root=task.corpus_root,
        )
    except Exception as error:
        raise RuntimeError(f"failed to compile {task.document.doc_id}: {error}") from error
    return {
        "doc_id": tree.doc_id,
        "schema_version": tree.schema_version,
        "compiler_version": tree.compiler_version,
        "tree_json": tree.model_dump_json(),
    }


def _compile_rows(tasks: Sequence[CompileTask], workers: int) -> Iterator[dict[str, str]]:
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if workers == 1:
        for task in tasks:
            yield _compile_row(task)
        return

    task_iterator = iter(tasks)
    with ProcessPoolExecutor(max_workers=workers) as executor:
        pending: set[Future[dict[str, str]]] = {
            executor.submit(_compile_row, task)
            for task in islice(task_iterator, workers * POOL_QUEUE_FACTOR)
        }
        while pending:
            completed, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                row = future.result()
                try:
                    task = next(task_iterator)
                except StopIteration:
                    pass
                else:
                    pending.add(executor.submit(_compile_row, task))
                yield row


def _batches(rows: Iterator[dict[str, str]], batch_size: int) -> Iterator[list[dict[str, str]]]:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    while batch := list(islice(rows, batch_size)):
        yield batch


def load_document_trees(
    database_url: str,
    corpus_root: Path,
    *,
    workers: int | None = None,
    batch_size: int = 50,
    progress_every: int = 100,
) -> int:
    if workers is None:
        workers = _default_workers()
    corpus_root = corpus_root.resolve()
    documents = _read_documents(corpus_root)
    directories = _index_document_directories(corpus_root)
    tasks: list[CompileTask] = []
    for document in documents:
        directory = directories.get(_nfc(document.file_path))
        if directory is None:
            raise FileNotFoundError(f"manifest directory not found: {document.file_path}")
        tasks.append(CompileTask(document=document, directory=directory, corpus_root=corpus_root))

    create_table_sql = read_sql("007_create_document_tree.sql")
    upsert_tree_sql = read_sql("008_upsert_document_tree.sql")
    loaded = 0
    with psycopg.connect(database_url) as connection:
        connection.execute(create_table_sql)
        with connection.cursor() as cursor:
            rows = _compile_rows(tasks, workers)
            for batch in _batches(rows, batch_size):
                cursor.executemany(upsert_tree_sql, batch)
                loaded += len(batch)
                if progress_every > 0 and loaded % progress_every == 0:
                    print(f"loaded {loaded}/{len(documents)} document trees", flush=True)

            cursor.execute(
                """
                SELECT source.doc_id
                FROM unnest(%s::text[]) AS source(doc_id)
                LEFT JOIN corpus.document_tree AS tree USING (doc_id)
                WHERE tree.doc_id IS NULL
                LIMIT 20
                """,
                ([document.doc_id for document in documents],),
            )
            missing = [str(row[0]) for row in cursor.fetchall()]
            if missing:
                raise RuntimeError(f"DocumentTree rows missing after load: {missing}")
    return loaded


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile and upsert DocumentTree JSONB rows.")
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
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--progress-every", type=int, default=100)
    arguments = parser.parse_args()

    loaded = load_document_trees(
        arguments.database_url,
        arguments.corpus_root,
        workers=arguments.workers,
        batch_size=arguments.batch_size,
        progress_every=arguments.progress_every,
    )
    print(json.dumps({"document_trees": loaded}))


if __name__ == "__main__":
    main()

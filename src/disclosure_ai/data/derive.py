"""Materialize semantic structural IR under corpus/derived."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import sys
import tempfile
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from disclosure_ai.data.catalog import CorpusCatalog, CorpusDocument
from disclosure_ai.data.parser import parse_artifact
from disclosure_ai.data.semantic_ir import SCHEMA_VERSION, build_semantic_ir

DERIVED_LAYOUT = "semantic-structural-ir-v1"


@dataclass(frozen=True, slots=True)
class DeriveSummary:
    documents_seen: int
    artifacts_written: int
    artifacts_skipped: int
    source_bytes: int
    output_bytes: int
    elapsed_seconds: float
    derived_root: str
    index_path: str


def derive_corpus(
    corpus_root: Path | str,
    *,
    output_root: Path | str | None = None,
    groups: set[str] | None = None,
    receipts: set[str] | None = None,
    force: bool = False,
    pretty: bool = False,
    compressed: bool = False,
    durable: bool = False,
    limit: int | None = None,
    progress_every: int = 25,
) -> DeriveSummary:
    corpus = Path(corpus_root).resolve()
    catalog = CorpusCatalog(corpus)
    derived_root = (
        Path(output_root).resolve()
        if output_root is not None
        else corpus / "derived" / DERIVED_LAYOUT
    )
    derived_root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    documents_seen = 0
    written = 0
    skipped = 0
    source_bytes = 0
    output_bytes = 0
    complete_run = groups is None and receipts is None and limit is None
    success_path = derived_root / "_SUCCESS.json"
    if complete_run:
        success_path.unlink(missing_ok=True)
    index_path = derived_root / "manifest.jsonl"
    existing_index = _load_index(index_path)
    index_records = {} if complete_run else dict(existing_index)

    for document in _selected_documents(catalog, groups=groups, receipts=receipts):
        if limit is not None and documents_seen >= limit:
            break
        documents_seen += 1
        expected_files = int(document.metadata.get("n_files", 0))
        if not document.artifacts or len(document.artifacts) != expected_files:
            receipt = document.metadata.get("rcept_no")
            raise RuntimeError(
                f"artifact count mismatch for {receipt}: "
                f"manifest={expected_files}, discovered={len(document.artifacts)}"
            )
        for artifact in document.artifacts:
            source_bytes += artifact.envelope.byte_size
            source_key = artifact.envelope.relative_path
            target = derived_path(
                derived_root,
                artifact.envelope.relative_path,
                compressed=compressed,
            )
            existing_record = existing_index.get(source_key)
            if not force and _is_current(
                target,
                artifact.envelope.sha256,
                derived_root=derived_root,
                index_record=existing_record,
            ):
                skipped += 1
                record = (
                    existing_record
                    if existing_record is not None
                    else _index_record_from_file(target, derived_root)
                )
                index_records[str(record["source_path"])] = record
                continue

            parsed = parse_artifact(artifact)
            ir = build_semantic_ir(parsed, document.metadata)
            output_bytes += _atomic_json_write(
                target,
                ir,
                pretty=pretty,
                durable=durable,
                compressed=compressed,
            )
            written += 1
            record = _index_record(ir, target, derived_root)
            index_records[str(record["source_path"])] = record

        if progress_every > 0 and documents_seen % progress_every == 0:
            elapsed = time.monotonic() - started
            print(
                f"documents={documents_seen} written={written} skipped={skipped} "
                f"elapsed={elapsed:.1f}s",
                file=sys.stderr,
                flush=True,
            )

    output_bytes += _atomic_jsonl_write(
        index_path,
        [index_records[key] for key in sorted(index_records)],
        durable=durable,
    )
    summary = DeriveSummary(
        documents_seen=documents_seen,
        artifacts_written=written,
        artifacts_skipped=skipped,
        source_bytes=source_bytes,
        output_bytes=output_bytes,
        elapsed_seconds=round(time.monotonic() - started, 3),
        derived_root=str(derived_root),
        index_path=str(index_path),
    )
    run_record = {
        "schema_version": SCHEMA_VERSION,
        "complete": complete_run,
        "compressed": compressed,
        **asdict(summary),
    }
    _atomic_json_write(
        derived_root / "_RUN.json",
        run_record,
        pretty=True,
        durable=durable,
        compressed=False,
    )
    if complete_run:
        _atomic_json_write(
            success_path,
            run_record,
            pretty=True,
            durable=durable,
            compressed=False,
        )
    return summary


def derived_path(derived_root: Path, raw_relative_path: str, *, compressed: bool = False) -> Path:
    relative = Path(raw_relative_path)
    if not relative.parts or relative.parts[0] != "raw":
        raise ValueError(f"expected raw-relative path, got {raw_relative_path!r}")
    mirrored = Path(*relative.parts[1:])
    suffix = ".semantic.json.gz" if compressed else ".semantic.json"
    return derived_root / mirrored.parent / f"{mirrored.name}{suffix}"


def _selected_documents(
    catalog: CorpusCatalog,
    *,
    groups: set[str] | None,
    receipts: set[str] | None,
) -> Iterator[CorpusDocument]:
    yield from catalog.iter_documents(groups=groups, receipts=receipts)


def _is_current(
    path: Path,
    source_sha256: str,
    *,
    derived_root: Path,
    index_record: dict[str, Any] | None,
) -> bool:
    if not path.is_file():
        return False
    if index_record is not None:
        expected_path = str(path.relative_to(derived_root))
        expected_size = index_record.get("derived_byte_size")
        expected_hash = index_record.get("derived_sha256")
        return bool(
            index_record.get("schema_version") == SCHEMA_VERSION
            and index_record.get("source_sha256") == source_sha256
            and index_record.get("derived_path") == expected_path
            and isinstance(expected_size, int)
            and path.stat().st_size == expected_size
            and isinstance(expected_hash, str)
            and _file_sha256(path) == expected_hash
        )
    try:
        with _open_text(path) as stream:
            value = json.load(stream)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return bool(
        isinstance(value, dict)
        and value.get("schema_version") == SCHEMA_VERSION
        and isinstance(value.get("source"), dict)
        and value["source"].get("sha256") == source_sha256
    )


def _index_record(ir: dict[str, Any], target: Path, derived_root: Path) -> dict[str, Any]:
    source = ir["source"]
    diagnostics = ir["diagnostics"]
    return {
        "schema_version": ir["schema_version"],
        "source_path": source["relative_path"],
        "source_sha256": source["sha256"],
        "doc_group": source["doc_group"],
        "receipt_no": source["receipt_no"],
        "file_role": source["file_role"],
        "derived_path": str(target.relative_to(derived_root)),
        "derived_byte_size": target.stat().st_size,
        "derived_sha256": _file_sha256(target),
        "section_count": len(ir["sections"]),
        "semantic_field_count": len(ir["semantic_fields"]),
        "block_count": len(ir["blocks"]),
        "parser_recovery_event_count": diagnostics["parser_recovery_event_count"],
        "unmapped_text_block_count": diagnostics["unmapped_text_block_count"],
    }


def _index_record_from_file(target: Path, derived_root: Path) -> dict[str, Any]:
    with _open_text(target) as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"derived artifact is not an object: {target}")
    return _index_record(value, target, derived_root)


def _load_index(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    records: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict) or not isinstance(value.get("source_path"), str):
                raise ValueError(f"invalid derived manifest line {line_number}: {path}")
            records[value["source_path"]] = value
    return records


def _atomic_json_write(
    path: Path,
    value: Any,
    *,
    pretty: bool,
    durable: bool,
    compressed: bool,
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        if compressed:
            with os.fdopen(fd, "wb") as raw_stream:
                with gzip.GzipFile(
                    filename="",
                    mode="wb",
                    fileobj=raw_stream,
                    mtime=0,
                ) as gzip_stream:
                    with io.TextIOWrapper(
                        gzip_stream,
                        encoding="utf-8",
                        newline="\n",
                    ) as stream:
                        _dump_json(value, stream, pretty=pretty)
                raw_stream.flush()
                if durable:
                    os.fsync(raw_stream.fileno())
        else:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                _dump_json(value, stream, pretty=pretty)
                stream.flush()
                if durable:
                    os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return path.stat().st_size


def _dump_json(value: Any, stream: Any, *, pretty: bool) -> None:
    json.dump(
        value,
        stream,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )
    stream.write("\n")


def _open_text(path: Path) -> Any:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_jsonl_write(path: Path, records: list[dict[str, Any]], *, durable: bool) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                stream.write("\n")
            stream.flush()
            if durable:
                os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return path.stat().st_size


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", help="path to corpus/ (containing raw/ and manifest.jsonl)")
    parser.add_argument("--output", help="override derived output root")
    parser.add_argument(
        "--group",
        action="append",
        choices=("periodic", "major", "exchange", "holding"),
        help="derive only this group; repeat to select multiple groups",
    )
    parser.add_argument(
        "--receipt",
        action="append",
        help="derive only this receipt number; repeat to select multiple receipts",
    )
    parser.add_argument("--force", action="store_true", help="rewrite current derived files")
    parser.add_argument("--pretty", action="store_true", help="write indented JSON (larger)")
    parser.add_argument(
        "--gzip",
        action="store_true",
        help="write deterministic .json.gz artifacts (recommended for the complete corpus)",
    )
    parser.add_argument(
        "--fsync",
        action="store_true",
        help="fsync every output before rename (safer on power loss, much slower)",
    )
    parser.add_argument("--limit", type=int, help="maximum selected documents to process")
    parser.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="print progress every N documents; use 0 to disable",
    )
    args = parser.parse_args()
    summary = derive_corpus(
        args.corpus,
        output_root=args.output,
        groups=set(args.group) if args.group else None,
        receipts=set(args.receipt) if args.receipt else None,
        force=args.force,
        pretty=args.pretty,
        compressed=args.gzip,
        durable=args.fsync,
        limit=args.limit,
        progress_every=args.progress_every,
    )
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

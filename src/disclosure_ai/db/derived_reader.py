"""Read only completed, hash-verified semantic IR materializations."""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TextIO

from disclosure_ai.data.semantic_ir import SCHEMA_VERSION


class IncompleteDerivedError(RuntimeError):
    pass


def completed_derived_root(corpus_root: Path | str) -> Path:
    root = Path(corpus_root).resolve() / "derived" / "semantic-structural-ir-v1"
    success_path = root / "_SUCCESS.json"
    manifest_path = root / "manifest.jsonl"
    if not success_path.is_file() or not manifest_path.is_file():
        raise IncompleteDerivedError(
            f"derived corpus is not complete: {success_path} and {manifest_path} are required"
        )
    success = _read_json(success_path)
    if success.get("complete") is not True or success.get("schema_version") != SCHEMA_VERSION:
        raise IncompleteDerivedError(f"invalid completion marker: {success_path}")
    return root


def iter_verified_entries(corpus_root: Path | str) -> Iterator[tuple[dict[str, Any], Path]]:
    root = completed_derived_root(corpus_root)
    with (root / "manifest.jsonl").open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            index = json.loads(line)
            if not isinstance(index, dict):
                raise ValueError(f"derived manifest line {line_number} is not an object")
            target = (root / str(index["derived_path"])).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                raise ValueError(f"invalid derived path on line {line_number}: {target}")
            if target.stat().st_size != int(index["derived_byte_size"]):
                raise ValueError(f"derived size mismatch: {target}")
            if _sha256(target) != str(index["derived_sha256"]):
                raise ValueError(f"derived hash mismatch: {target}")
            yield index, target


def read_verified_ir(index: dict[str, Any], target: Path) -> dict[str, Any]:
    with _open_text(target) as artifact_stream:
        value = json.load(artifact_stream)
    if not isinstance(value, dict):
        raise ValueError(f"semantic IR is not an object: {target}")
    ir: dict[str, Any] = value
    _validate_ir(ir, index, target)
    return ir


def iter_verified_ir(corpus_root: Path | str) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    for index, target in iter_verified_entries(corpus_root):
        yield index, read_verified_ir(index, target)


def _validate_ir(ir: Any, index: dict[str, Any], target: Path) -> None:
    if not isinstance(ir, dict) or ir.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"invalid semantic IR schema: {target}")
    source = ir.get("source")
    diagnostics = ir.get("diagnostics")
    if not isinstance(source, dict) or not isinstance(diagnostics, dict):
        raise ValueError(f"missing source/diagnostics: {target}")
    if source.get("relative_path") != index.get("source_path"):
        raise ValueError(f"source path mismatch: {target}")
    if source.get("sha256") != index.get("source_sha256"):
        raise ValueError(f"source hash mismatch: {target}")
    if diagnostics.get("lossless_source_verified") is not True:
        raise ValueError(f"source lossless invariant was not verified: {target}")
    if diagnostics.get("all_non_whitespace_text_mapped") is not True:
        raise ValueError(f"semantic text coverage is incomplete: {target}")


def _open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

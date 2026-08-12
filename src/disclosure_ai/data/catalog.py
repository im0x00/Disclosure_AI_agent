"""Corpus discovery that preserves path bytes and source bytes exactly."""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from disclosure_ai.data.models import SourceArtifact, SourceEnvelope, SourceFormat

_RECEIPT_RE = re.compile(r"(?P<receipt>\d{14})")
_XML_ENCODING_RE = re.compile(rb"<\?xml[^>]*\bencoding\s*=\s*['\"]([^'\"]+)", re.I)
_HTML_ENCODING_RE = re.compile(rb"\bcharset\s*=\s*['\"]?([^\s'\";>]+)", re.I)


@dataclass(frozen=True, slots=True)
class CorpusDocument:
    metadata: Mapping[str, Any]
    artifacts: tuple[SourceArtifact, ...]


class CorpusCatalog:
    """Index the corpus without normalizing away filesystem or byte identity."""

    def __init__(self, corpus_root: Path | str) -> None:
        self.corpus_root = Path(corpus_root).resolve()
        self.raw_root = self.corpus_root / "raw"
        self.manifest_path = self.corpus_root / "manifest.jsonl"

    def iter_paths(self, *, include_list_sidecars: bool = True) -> Iterator[Path]:
        for path in sorted(self.raw_root.rglob("*"), key=os.fsencode):
            if not path.is_file():
                continue
            if not include_list_sidecars and path.name.startswith("list_"):
                continue
            yield path

    def read_artifact(self, path: Path | str) -> SourceArtifact:
        absolute_path = Path(path).resolve()
        relative = absolute_path.relative_to(self.corpus_root)
        content = absolute_path.read_bytes()
        parts = relative.parts
        part_bytes = tuple(os.fsencode(part) for part in parts)
        group = parts[1] if len(parts) >= 2 and parts[0] == "raw" else None
        corp = parts[2] if len(parts) >= 3 and parts[0] == "raw" else None
        receipt_folder = parts[3] if len(parts) >= 4 and parts[0] == "raw" else None
        receipt_no = self._receipt_no(receipt_folder, absolute_path.name)
        attachment_code, role = self._file_role(absolute_path, receipt_no)
        detected_format = self._detect_format(content, absolute_path.suffix)
        envelope = SourceEnvelope(
            absolute_path=absolute_path,
            relative_path=str(relative),
            relative_path_bytes=os.fsencode(str(relative)),
            path_parts=parts,
            path_parts_bytes=part_bytes,
            normalized_nfc_path=unicodedata.normalize("NFC", str(relative)),
            sha256=hashlib.sha256(content).hexdigest(),
            byte_size=len(content),
            doc_group=group,
            corp_folder=corp,
            corp_folder_nfc=unicodedata.normalize("NFC", corp) if corp else None,
            receipt_folder=receipt_folder,
            receipt_no=receipt_no,
            file_name=absolute_path.name,
            file_name_bytes=os.fsencode(absolute_path.name),
            file_role=role,
            attachment_code=attachment_code,
            detected_format=detected_format,
            detected_encoding=self._detect_encoding(content, detected_format),
            declared_encoding=self._declared_encoding(content),
        )
        return SourceArtifact(envelope=envelope, content=content)

    def iter_artifacts(self, *, include_list_sidecars: bool = True) -> Iterator[SourceArtifact]:
        for path in self.iter_paths(include_list_sidecars=include_list_sidecars):
            yield self.read_artifact(path)

    def iter_manifest(self) -> Iterator[dict[str, Any]]:
        with self.manifest_path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError(f"manifest line {line_number} is not an object")
                yield record

    def iter_documents(
        self,
        *,
        groups: set[str] | None = None,
        receipts: set[str] | None = None,
    ) -> Iterator[CorpusDocument]:
        by_key = self._artifact_index()

        for metadata in self.iter_manifest():
            group = str(metadata["doc_group"])
            receipt = str(metadata["rcept_no"])
            if groups is not None and group not in groups:
                continue
            if receipts is not None and receipt not in receipts:
                continue
            key = (group, receipt)
            paths = by_key.get(key, [])
            artifacts = tuple(self.read_artifact(path) for path in sorted(paths, key=os.fsencode))
            yield CorpusDocument(metadata=metadata, artifacts=artifacts)

    def read_document(self, doc_group: str, receipt_no: str) -> CorpusDocument:
        metadata = next(
            (
                record
                for record in self.iter_manifest()
                if record.get("doc_group") == doc_group and record.get("rcept_no") == receipt_no
            ),
            None,
        )
        if metadata is None:
            raise KeyError(f"manifest has no {doc_group}/{receipt_no}")
        paths = self._artifact_index().get((doc_group, receipt_no), [])
        artifacts = tuple(self.read_artifact(path) for path in sorted(paths, key=os.fsencode))
        return CorpusDocument(metadata=metadata, artifacts=artifacts)

    def _artifact_index(self) -> dict[tuple[str, str], list[Path]]:
        by_key: dict[tuple[str, str], list[Path]] = {}
        for path in self.iter_paths(include_list_sidecars=False):
            relative = path.relative_to(self.corpus_root)
            parts = relative.parts
            if len(parts) < 5 or parts[0] != "raw":
                continue
            receipt_no = self._receipt_no(parts[3], path.name)
            if receipt_no is not None:
                by_key.setdefault((parts[1], receipt_no), []).append(path)
        return by_key

    @staticmethod
    def _receipt_no(receipt_folder: str | None, file_name: str) -> str | None:
        for value in (receipt_folder, file_name):
            if value is not None and (match := _RECEIPT_RE.search(value)):
                return match.group("receipt")
        return None

    @staticmethod
    def _file_role(path: Path, receipt_no: str | None) -> tuple[str | None, str]:
        stem = path.stem
        if path.name.startswith("list_"):
            return None, "list-api-sidecar"
        if receipt_no is None:
            return None, "unclassified"
        if stem == receipt_no:
            return None, "primary"
        prefix = f"{receipt_no}_"
        if stem.startswith(prefix):
            code = stem[len(prefix) :]
            if code == "viewer":
                return code, "viewer-html"
            return code, "attachment"
        return None, "unclassified"

    @staticmethod
    def _detect_format(content: bytes, suffix: str) -> SourceFormat:
        head = content[:4096].lstrip(b"\xef\xbb\xbf\x00\t\r\n ").lower()
        if content.startswith(b"%PDF-"):
            return SourceFormat.PDF
        if head.startswith((b"<html", b"<!doctype html")):
            return SourceFormat.HTML
        if head.startswith(b"<?xml") or head.startswith(b"<document"):
            return SourceFormat.DART_MARKUP
        if suffix.lower() == ".json" or head.startswith((b"{", b"[")):
            return SourceFormat.JSON
        return SourceFormat.UNKNOWN

    @staticmethod
    def _detect_encoding(content: bytes, source_format: SourceFormat) -> str | None:
        if source_format is SourceFormat.PDF:
            return None
        if content.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content.decode("cp949")
            except UnicodeDecodeError:
                return None
            return "cp949"
        return "utf-8"

    @staticmethod
    def _declared_encoding(content: bytes) -> str | None:
        head = content[:4096]
        match = _XML_ENCODING_RE.search(head) or _HTML_ENCODING_RE.search(head)
        return match.group(1).decode("ascii", errors="replace").lower() if match else None

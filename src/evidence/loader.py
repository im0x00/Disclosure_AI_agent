from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SQL_ROOT = Path(__file__).resolve().parents[1] / "sql"
DEFAULT_DATABASE_URL = "postgresql://disclosure_ai:local-dev-only@localhost:5432/disclosure_ai"


def read_sql(name: str) -> str:
    return (SQL_ROOT / name).read_text(encoding="utf-8")


def optional_text(value: str | None) -> str | None:
    return value if value else None


def optional_integer(value: str | int | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def read_companies(corpus_root: Path) -> list[dict[str, Any]]:
    with (corpus_root / "universe.csv").open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))

    return [
        {
            "corp_code": row["corp_code"],
            "stock_code": row["stock_code"],
            "corp_name": row["corp_name"],
            "listed_name": row["listed_name"],
            "corp_eng_name": optional_text(row["corp_eng_name"]),
            "market": row["market"],
            "industry": row["industry"],
            "sector_no": int(row["sector_no"]),
            "sector": row["sector"],
            "listing_date": date.fromisoformat(row["listing_date"]),
            "fiscal_month": row["fiscal_month"],
            "market_cap": optional_integer(row["market_cap"]),
            "n_periodic": int(row["n_periodic"]),
            "n_major": int(row["n_major"]),
            "n_exchange": int(row["n_exchange"]),
            "n_holding": int(row["n_holding"]),
            "note": optional_text(row["note"]),
        }
        for row in rows
    ]


def parse_receipt_date(value: str) -> date:
    return date(int(value[0:4]), int(value[4:6]), int(value[6:8]))


def read_documents(corpus_root: Path) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    with (corpus_root / "manifest.jsonl").open(encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            documents.append(
                {
                    "doc_id": row["doc_id"],
                    "corp_code": row["corp_code"],
                    "doc_group": row["doc_group"],
                    "doc_subtype": row["doc_subtype"],
                    "report_name": row["report_nm"],
                    "is_correction": row["is_correction"],
                    "receipt_no": row["rcept_no"],
                    "receipt_date": parse_receipt_date(row["rcept_dt"]),
                    "filer_name": row["flr_nm"],
                    "base_year": optional_integer(row.get("base_year")),
                    "base_month": optional_integer(row.get("base_month")),
                    "file_path": row["file_path"],
                    "file_format": row["file_format"],
                    "file_count": int(row["n_files"]),
                }
            )
    return documents


def nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def index_document_directories(corpus_root: Path) -> dict[str, Path]:
    raw_root = corpus_root / "raw"
    result: dict[str, Path] = {}
    for group in raw_root.iterdir():
        if not group.is_dir():
            continue
        for company in group.iterdir():
            if not company.is_dir():
                continue
            for document_directory in company.iterdir():
                if not document_directory.is_dir():
                    continue
                relative = document_directory.relative_to(corpus_root).as_posix()
                normalized = nfc(relative)
                if normalized in result:
                    raise ValueError(f"duplicate NFC document path: {normalized}")
                result[normalized] = document_directory
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_role(path: Path, receipt_no: str) -> str:
    if path.stem == receipt_no:
        return "primary"
    if path.name == f"{receipt_no}_viewer.html":
        return "viewer"
    return "attachment"


def iter_artifacts(
    corpus_root: Path,
    documents: list[dict[str, Any]],
) -> Iterator[dict[str, Any]]:
    directories = index_document_directories(corpus_root)
    for position, document in enumerate(documents, start=1):
        normalized_directory = nfc(str(document["file_path"]))
        directory = directories.get(normalized_directory)
        if directory is None:
            raise FileNotFoundError(f"manifest directory not found: {normalized_directory}")

        files = sorted(
            path for path in directory.iterdir() if path.is_file() and not path.name.startswith(".")
        )
        if len(files) != document["file_count"]:
            raise ValueError(
                f"file count mismatch for {document['doc_id']}: "
                f"manifest={document['file_count']} actual={len(files)}"
            )

        for path in files:
            source_path = path.relative_to(corpus_root).as_posix()
            source_path_nfc = nfc(source_path)
            yield {
                "artifact_id": source_path_nfc,
                "doc_id": document["doc_id"],
                "source_path": source_path,
                "source_path_nfc": source_path_nfc,
                "file_name": path.name,
                "source_format": path.suffix.lower().lstrip(".") or "unknown",
                "artifact_role": artifact_role(path, str(document["receipt_no"])),
                "byte_size": path.stat().st_size,
                "sha256": sha256_file(path),
            }

        if position % 500 == 0:
            print(f"scanned {position}/{len(documents)} documents", flush=True)


def load_catalog(
    database_url: str,
    companies: Sequence[Mapping[str, Any]],
    documents: Sequence[Mapping[str, Any]],
    artifacts: Sequence[Mapping[str, Any]],
) -> tuple[int, int, int]:
    with psycopg.connect(database_url) as connection:
        connection.execute(read_sql("001_create_corpus_catalog.sql"))
        with connection.cursor() as cursor:
            cursor.executemany(read_sql("002_upsert_company.sql"), companies)
            cursor.executemany(read_sql("003_upsert_disclosure_document.sql"), documents)
            cursor.executemany(read_sql("004_upsert_source_artifact.sql"), artifacts)
            cursor.execute(read_sql("005_verify_corpus_catalog.sql"))
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("catalog verification returned no row")
            return int(row[0]), int(row[1]), int(row[2])


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the corpus catalog into PostgreSQL.")
    parser.add_argument("--corpus-root", type=Path, default=PROJECT_ROOT / "corpus")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    arguments = parser.parse_args()

    corpus_root = arguments.corpus_root.resolve()
    companies = read_companies(corpus_root)
    documents = read_documents(corpus_root)
    company_codes = {company["corp_code"] for company in companies}
    unknown_codes = sorted({document["corp_code"] for document in documents} - company_codes)
    if unknown_codes:
        raise ValueError(f"manifest contains unknown corp_code values: {unknown_codes}")

    artifacts = list(iter_artifacts(corpus_root, documents))
    counts = load_catalog(arguments.database_url, companies, documents, artifacts)
    print(
        json.dumps(
            {"companies": counts[0], "documents": counts[1], "artifacts": counts[2]},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

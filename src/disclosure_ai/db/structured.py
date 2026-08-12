"""Readers for the corpus's pre-existing structured datasets."""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_FISCAL_MONTH_RE = re.compile(r"^(\d{1,2})월$")


def normalize_forms(value: str | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    return unicodedata.normalize("NFC", value), unicodedata.normalize("NFD", value)


def read_companies(corpus_root: Path | str) -> Iterator[dict[str, Any]]:
    path = Path(corpus_root) / "universe.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            yield company_record(row)


def read_documents(corpus_root: Path | str) -> Iterator[dict[str, Any]]:
    path = Path(corpus_root) / "manifest.jsonl"
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"manifest line {line_number} is not an object")
            yield document_record(value)


def company_record(row: dict[str, str]) -> dict[str, Any]:
    corp_nfc, corp_nfd = normalize_forms(row["corp_name"])
    listed_nfc, listed_nfd = normalize_forms(row["listed_name"])
    month_match = _FISCAL_MONTH_RE.fullmatch(row["fiscal_month"])
    if month_match is None:
        raise ValueError(f"invalid fiscal_month: {row['fiscal_month']!r}")
    return {
        "corp_code": row["corp_code"],
        "stock_code": row["stock_code"],
        "corp_name": row["corp_name"],
        "corp_name_nfc": corp_nfc,
        "corp_name_nfd": corp_nfd,
        "listed_name": row["listed_name"],
        "listed_name_nfc": listed_nfc,
        "listed_name_nfd": listed_nfd,
        "corp_eng_name": _optional(row["corp_eng_name"]),
        "market": _optional(row["market"]),
        "industry": _optional(row["industry"]),
        "sector_no": _optional_int(row["sector_no"]),
        "sector": _optional(row["sector"]),
        "listing_date": row["listing_date"],
        "fiscal_month": int(month_match.group(1)),
        "market_cap": _optional_int(row["market_cap"]),
        "n_periodic": int(row["n_periodic"]),
        "n_major": int(row["n_major"]),
        "n_exchange": int(row["n_exchange"]),
        "n_holding": int(row["n_holding"]),
        "note": _optional(row["note"]),
        "source_record": row,
    }


def document_record(row: dict[str, Any]) -> dict[str, Any]:
    corp_nfc, corp_nfd = normalize_forms(str(row["corp_name"]))
    report_nfc, report_nfd = normalize_forms(str(row["report_nm"]))
    filer_nfc, filer_nfd = normalize_forms(str(row["flr_nm"]))
    path_nfc, path_nfd = normalize_forms(str(row["file_path"]))
    return {
        **row,
        "corp_name_nfc": corp_nfc,
        "corp_name_nfd": corp_nfd,
        "report_nm_nfc": report_nfc,
        "report_nm_nfd": report_nfd,
        "flr_nm_nfc": filer_nfc,
        "flr_nm_nfd": filer_nfd,
        "file_path_nfc": path_nfc,
        "file_path_nfd": path_nfd,
        "source_record": row,
    }


def name_aliases(company: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "entity_type": "company",
            "entity_key": str(company["corp_code"]),
            "name_kind": kind,
            "name_raw": str(company[field]),
            "name_nfc": str(company[f"{field}_nfc"]),
            "name_nfd": str(company[f"{field}_nfd"]),
        }
        for kind, field in (("corp_name", "corp_name"), ("listed_name", "listed_name"))
    ]


def _optional(value: str) -> str | None:
    return value if value != "" else None


def _optional_int(value: str) -> int | None:
    return int(value) if value != "" else None

import json
from pathlib import Path

from evidence.validate_corpus import validate_corpus


def write_manifest(corpus_root: Path, rows: list[dict[str, object]]) -> None:
    corpus_root.mkdir()
    (corpus_root / "manifest.jsonl").write_text(
        "".join(f"{json.dumps(row)}\n" for row in rows),
        encoding="utf-8",
    )


def test_validates_every_manifest_document_and_skips_pdf(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    first_path = "raw/exchange/Acme/20230101000001"
    second_path = "raw/periodic/Acme/20230102000002"
    write_manifest(
        corpus_root,
        [
            {"doc_id": "exchange_20230101000001", "file_path": first_path, "n_files": 1},
            {"doc_id": "periodic_20230102000002", "file_path": second_path, "n_files": 2},
        ],
    )

    first_directory = corpus_root / first_path
    first_directory.mkdir(parents=True)
    (first_directory / "20230101000001.xml").write_text(
        "<html><body><p>AT&T, Alpha &amp; Beta</p></body></html>",
        encoding="utf-8",
    )

    second_directory = corpus_root / second_path
    second_directory.mkdir(parents=True)
    (second_directory / "20230102000002.pdf").write_bytes(b"raw PDF backup")
    (second_directory / "20230102000002_viewer.html").write_text(
        "<html><body><h1>Fallback</h1></body></html>",
        encoding="utf-8",
    )

    report = validate_corpus(corpus_root, progress_every=0)

    assert report.passed
    assert report.manifest_documents == 2
    assert report.filesystem_documents == 2
    assert report.source_artifacts == 3
    assert report.expected_tree_artifacts == 2
    assert report.compiled_tree_artifacts == 2
    assert report.validated_nodes > 0
    assert report.validated_texts == 6
    assert not report.failures


def test_reports_incompatible_document_without_stopping_the_scan(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    source_path = "raw/exchange/Acme/20230101000001"
    write_manifest(
        corpus_root,
        [{"doc_id": "exchange_20230101000001", "file_path": source_path, "n_files": 2}],
    )
    source_directory = corpus_root / source_path
    source_directory.mkdir(parents=True)
    (source_directory / "20230101000001.xml").write_text(
        "<html><body>only one file</body></html>",
        encoding="utf-8",
    )

    report = validate_corpus(corpus_root, progress_every=0)

    assert not report.passed
    assert len(report.failures) == 1
    assert report.failures[0].doc_id == "exchange_20230101000001"
    assert report.failures[0].error_type == "ValueError"
    assert "file count mismatch" in report.failures[0].message

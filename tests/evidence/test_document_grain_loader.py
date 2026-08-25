from pathlib import Path

from evidence.document_grain_loader import CompileGrainsTask, _compile_documents


def test_compile_documents_uses_picklable_process_pool_tasks(tmp_path: Path) -> None:
    tasks: list[CompileGrainsTask] = []
    for receipt_no in ("20240101000001", "20240101000002"):
        directory = tmp_path / "raw" / "major" / "Acme" / receipt_no
        directory.mkdir(parents=True)
        (directory / f"{receipt_no}.xml").write_text(
            (
                "<DOCUMENT><BODY><SECTION-1>"
                f'<TITLE ATOC="Y">Report {receipt_no}</TITLE>'
                "<P>Pool-safe content.</P>"
                "</SECTION-1></BODY></DOCUMENT>"
            ),
            encoding="utf-8",
        )
        tasks.append(
            CompileGrainsTask(
                doc_id=f"major_{receipt_no}",
                directory=directory,
                corpus_root=tmp_path,
                max_estimated_tokens=100,
            )
        )

    compiled = tuple(_compile_documents(tasks, workers=2))

    assert {document.doc_id for document in compiled} == {
        "major_20240101000001",
        "major_20240101000002",
    }
    assert all(document.rows for document in compiled)

from pathlib import Path

from evidence.loader import artifact_role, read_companies, read_documents, read_sql

CORPUS_ROOT = Path(__file__).resolve().parents[2] / "corpus"


def test_catalog_inputs_have_expected_counts() -> None:
    assert len(read_companies(CORPUS_ROOT)) == 70
    assert len(read_documents(CORPUS_ROOT)) == 4_204


def test_selected_sample_is_a_single_file_non_correction_disclosure() -> None:
    documents = {document["doc_id"]: document for document in read_documents(CORPUS_ROOT)}
    sample = documents["exchange_20230630800101"]

    assert sample["doc_group"] == "exchange"
    assert sample["is_correction"] is False
    assert sample["file_count"] == 1


def test_artifact_role_uses_receipt_number() -> None:
    receipt_no = "20230630800101"

    assert artifact_role(Path(f"{receipt_no}.xml"), receipt_no) == "primary"
    assert artifact_role(Path(f"{receipt_no}_viewer.html"), receipt_no) == "viewer"
    assert artifact_role(Path(f"{receipt_no}_00760.xml"), receipt_no) == "attachment"


def test_sql_files_are_loaded_from_src_layout() -> None:
    statement = read_sql("010_upsert_document_grain.sql")

    assert "INSERT INTO corpus.document_grain" in statement

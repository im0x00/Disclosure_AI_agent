SELECT
    document.doc_id,
    document.report_name,
    document.receipt_date,
    artifact.artifact_role,
    artifact.source_path_nfc,
    artifact.byte_size,
    artifact.sha256
FROM corpus.disclosure_document AS document
JOIN corpus.source_artifact AS artifact USING (doc_id)
WHERE document.doc_id = 'exchange_20230630800101';

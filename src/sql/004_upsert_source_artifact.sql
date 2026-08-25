-- artifact_id is the NFC-normalized path relative to corpus/.
INSERT INTO corpus.source_artifact (
    artifact_id,
    doc_id,
    source_path,
    source_path_nfc,
    file_name,
    source_format,
    artifact_role,
    byte_size,
    sha256
) VALUES (
    %(artifact_id)s,
    %(doc_id)s,
    %(source_path)s,
    %(source_path_nfc)s,
    %(file_name)s,
    %(source_format)s,
    %(artifact_role)s,
    %(byte_size)s,
    %(sha256)s
)
ON CONFLICT (artifact_id) DO UPDATE SET
    doc_id = EXCLUDED.doc_id,
    source_path = EXCLUDED.source_path,
    source_path_nfc = EXCLUDED.source_path_nfc,
    file_name = EXCLUDED.file_name,
    source_format = EXCLUDED.source_format,
    artifact_role = EXCLUDED.artifact_role,
    byte_size = EXCLUDED.byte_size,
    sha256 = EXCLUDED.sha256;

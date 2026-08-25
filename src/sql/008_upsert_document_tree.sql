INSERT INTO corpus.document_tree (
    doc_id,
    schema_version,
    compiler_version,
    tree,
    compiled_at
) VALUES (
    %(doc_id)s,
    %(schema_version)s,
    %(compiler_version)s,
    %(tree_json)s::jsonb,
    now()
)
ON CONFLICT (doc_id) DO UPDATE SET
    schema_version = EXCLUDED.schema_version,
    compiler_version = EXCLUDED.compiler_version,
    tree = EXCLUDED.tree,
    compiled_at = EXCLUDED.compiled_at;

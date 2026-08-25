CREATE TABLE IF NOT EXISTS corpus.document_tree (
    doc_id text PRIMARY KEY
        REFERENCES corpus.disclosure_document (doc_id) ON DELETE CASCADE,
    schema_version text NOT NULL,
    compiler_version text NOT NULL,
    tree jsonb NOT NULL CHECK (jsonb_typeof(tree) = 'object'),
    compiled_at timestamptz NOT NULL DEFAULT now(),
    CHECK (tree ->> 'doc_id' = doc_id),
    CHECK (tree ->> 'schema_version' = schema_version),
    CHECK (tree ->> 'compiler_version' = compiler_version)
);

COMMENT ON TABLE corpus.document_tree IS
    'Versioned DocumentTree JSON compiled from one disclosure XML/HTML artifact set.';

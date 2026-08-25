CREATE TABLE IF NOT EXISTS corpus.document_grain (
    grain_id text PRIMARY KEY CHECK (grain_id ~ '^[0-9a-f]{64}$'),
    doc_id text NOT NULL
        REFERENCES corpus.disclosure_document (doc_id) ON DELETE CASCADE,
    artifact_id text NOT NULL
        REFERENCES corpus.source_artifact (artifact_id) ON DELETE CASCADE,
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    kind text NOT NULL CHECK (kind IN ('document', 'prose', 'table', 'image')),
    schema_version text NOT NULL,
    compiler_version text NOT NULL,
    core_text text NOT NULL CHECK (core_text <> ''),
    rendered_text text NOT NULL CHECK (rendered_text <> ''),
    estimated_tokens integer NOT NULL CHECK (estimated_tokens > 0),
    semantic_context jsonb NOT NULL CHECK (jsonb_typeof(semantic_context) = 'object'),
    source_address jsonb NOT NULL CHECK (jsonb_typeof(source_address) = 'object'),
    previous_grain_id text,
    next_grain_id text,
    compiled_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (doc_id, ordinal)
);

CREATE INDEX IF NOT EXISTS document_grain_document_idx
    ON corpus.document_grain (doc_id, ordinal);

CREATE INDEX IF NOT EXISTS document_grain_artifact_idx
    ON corpus.document_grain (artifact_id, ordinal);

CREATE INDEX IF NOT EXISTS document_grain_scope_idx
    ON corpus.document_grain ((source_address ->> 'scope_id'));

COMMENT ON TABLE corpus.document_grain IS
    'Runtime grains with non-overlapping core content, repeated semantic context, and exact source addresses.';

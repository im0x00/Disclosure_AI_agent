CREATE TABLE IF NOT EXISTS corpus.document_relation (
    relation_id text PRIMARY KEY CHECK (relation_id ~ '^[0-9a-f]{64}$'),
    source_doc_id text NOT NULL
        REFERENCES corpus.disclosure_document (doc_id) ON DELETE CASCADE,
    source_grain_ids text[] NOT NULL DEFAULT '{}'::text[],
    predicate text NOT NULL
        CHECK (predicate IN ('revises', 'references', 'terminates')),
    target_doc_id text NOT NULL
        REFERENCES corpus.disclosure_document (doc_id) ON DELETE CASCADE,
    target_grain_ids text[] NOT NULL DEFAULT '{}'::text[],
    built_at timestamptz NOT NULL DEFAULT now(),
    CHECK (source_doc_id <> target_doc_id),
    CHECK (array_position(source_grain_ids, NULL) IS NULL),
    CHECK (array_position(target_grain_ids, NULL) IS NULL)
);

CREATE INDEX IF NOT EXISTS document_relation_source_idx
    ON corpus.document_relation (source_doc_id, predicate);

CREATE INDEX IF NOT EXISTS document_relation_target_idx
    ON corpus.document_relation (target_doc_id, predicate);

COMMENT ON TABLE corpus.document_relation IS
    'Directed in-corpus document edges; empty grain arrays mean whole-document endpoints.';

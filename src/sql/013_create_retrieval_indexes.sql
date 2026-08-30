BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS corpus.document_grain_embedding (
    grain_id text NOT NULL
        REFERENCES corpus.document_grain(grain_id) ON DELETE CASCADE,
    model_id text NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions > 0),
    embedding vector NOT NULL,
    embedded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (grain_id, model_id),
    CHECK (vector_dims(embedding) = dimensions)
);

CREATE INDEX IF NOT EXISTS document_grain_rendered_text_trgm_idx
    ON corpus.document_grain
    USING gin (rendered_text gin_trgm_ops);

CREATE INDEX IF NOT EXISTS document_grain_rendered_text_fts_idx
    ON corpus.document_grain
    USING gin (to_tsvector('simple', rendered_text));

CREATE INDEX IF NOT EXISTS document_relation_source_grains_gin_idx
    ON corpus.document_relation
    USING gin (source_grain_ids);

CREATE INDEX IF NOT EXISTS document_relation_target_grains_gin_idx
    ON corpus.document_relation
    USING gin (target_grain_ids);

DROP FUNCTION IF EXISTS corpus.create_document_grain_embedding_index(text, integer);

CREATE OR REPLACE FUNCTION corpus.create_document_grain_embedding_index(
    requested_model_id text,
    requested_dimensions integer,
    requested_metric text
) RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    index_name text;
    operator_class text;
BEGIN
    IF requested_model_id IS NULL OR requested_model_id = '' THEN
        RAISE EXCEPTION 'model_id must not be empty';
    END IF;
    IF requested_dimensions <= 0 THEN
        RAISE EXCEPTION 'dimensions must be positive';
    END IF;
    operator_class := CASE requested_metric
        WHEN 'cosine' THEN 'vector_cosine_ops'
        WHEN 'inner_product' THEN 'vector_ip_ops'
        WHEN 'l2' THEN 'vector_l2_ops'
        ELSE NULL
    END;
    IF operator_class IS NULL THEN
        RAISE EXCEPTION 'unsupported vector metric: %', requested_metric;
    END IF;

    index_name := 'document_grain_embedding_hnsw_'
        || substr(
            md5(
                requested_model_id || ':' || requested_dimensions::text || ':'
                || requested_metric
            ),
            1,
            16
        );

    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS %I '
        || 'ON corpus.document_grain_embedding '
        || 'USING hnsw ((embedding::vector(%s)) %s) '
        || 'WHERE model_id = %L AND dimensions = %s',
        index_name,
        requested_dimensions,
        operator_class,
        requested_model_id,
        requested_dimensions
    );
    RETURN index_name;
END;
$$;

COMMIT;

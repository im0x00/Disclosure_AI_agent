INSERT INTO corpus.document_grain_embedding (
    grain_id,
    model_id,
    dimensions,
    embedding,
    embedded_at
) VALUES (
    %(grain_id)s,
    %(model_id)s,
    %(dimensions)s,
    %(embedding)s::vector,
    now()
)
ON CONFLICT (grain_id, model_id) DO UPDATE
SET dimensions = EXCLUDED.dimensions,
    embedding = EXCLUDED.embedding,
    embedded_at = EXCLUDED.embedded_at;

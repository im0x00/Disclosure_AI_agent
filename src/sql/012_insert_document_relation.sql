INSERT INTO corpus.document_relation (
    relation_id,
    source_doc_id,
    source_grain_ids,
    predicate,
    target_doc_id,
    target_grain_ids,
    built_at
) VALUES (
    %(relation_id)s,
    %(source_doc_id)s,
    %(source_grain_ids)s,
    %(predicate)s,
    %(target_doc_id)s,
    %(target_grain_ids)s,
    now()
);

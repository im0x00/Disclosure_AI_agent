SELECT
    (SELECT count(*) FROM corpus.company) AS companies,
    (SELECT count(*) FROM corpus.disclosure_document) AS documents,
    (SELECT count(*) FROM corpus.source_artifact) AS artifacts;

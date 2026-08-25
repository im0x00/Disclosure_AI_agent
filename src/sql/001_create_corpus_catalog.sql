CREATE SCHEMA IF NOT EXISTS corpus;

CREATE TABLE IF NOT EXISTS corpus.company (
    corp_code text PRIMARY KEY CHECK (corp_code ~ '^[0-9]{8}$'),
    stock_code text NOT NULL CHECK (stock_code ~ '^[0-9]{6}$'),
    corp_name text NOT NULL,
    listed_name text NOT NULL,
    corp_eng_name text,
    market text NOT NULL,
    industry text NOT NULL,
    sector_no integer NOT NULL,
    sector text NOT NULL,
    listing_date date NOT NULL,
    fiscal_month text NOT NULL,
    market_cap bigint,
    n_periodic integer NOT NULL CHECK (n_periodic >= 0),
    n_major integer NOT NULL CHECK (n_major >= 0),
    n_exchange integer NOT NULL CHECK (n_exchange >= 0),
    n_holding integer NOT NULL CHECK (n_holding >= 0),
    note text
);

CREATE TABLE IF NOT EXISTS corpus.disclosure_document (
    doc_id text PRIMARY KEY,
    corp_code text NOT NULL REFERENCES corpus.company (corp_code),
    doc_group text NOT NULL
        CHECK (doc_group IN ('periodic', 'major', 'exchange', 'holding')),
    doc_subtype text,
    report_name text NOT NULL,
    is_correction boolean NOT NULL,
    receipt_no text NOT NULL UNIQUE CHECK (receipt_no ~ '^[0-9]{14}$'),
    receipt_date date NOT NULL,
    filer_name text NOT NULL,
    base_year integer,
    base_month integer CHECK (base_month BETWEEN 1 AND 12),
    file_path text NOT NULL UNIQUE,
    file_format text NOT NULL,
    file_count integer NOT NULL CHECK (file_count > 0)
);

CREATE TABLE IF NOT EXISTS corpus.source_artifact (
    artifact_id text PRIMARY KEY,
    doc_id text NOT NULL
        REFERENCES corpus.disclosure_document (doc_id) ON DELETE CASCADE,
    source_path text NOT NULL,
    source_path_nfc text NOT NULL UNIQUE,
    file_name text NOT NULL,
    source_format text NOT NULL,
    artifact_role text NOT NULL
        CHECK (artifact_role IN ('primary', 'attachment', 'viewer')),
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    UNIQUE (doc_id, file_name)
);

CREATE INDEX IF NOT EXISTS disclosure_document_company_date_idx
    ON corpus.disclosure_document (corp_code, receipt_date);

CREATE INDEX IF NOT EXISTS disclosure_document_kind_idx
    ON corpus.disclosure_document (doc_group, doc_subtype);

CREATE INDEX IF NOT EXISTS source_artifact_document_idx
    ON corpus.source_artifact (doc_id);

COMMENT ON TABLE corpus.disclosure_document IS
    'One logical DART filing represented by one manifest.jsonl row.';

COMMENT ON TABLE corpus.source_artifact IS
    'One immutable raw file belonging to a disclosure document; bytes remain under corpus/raw.';

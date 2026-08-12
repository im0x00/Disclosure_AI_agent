CREATE SCHEMA IF NOT EXISTS disclosure;

CREATE TABLE IF NOT EXISTS disclosure.schema_migration (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS disclosure.company (
    corp_code text PRIMARY KEY CHECK (corp_code ~ '^[0-9]{8}$'),
    stock_code text NOT NULL CHECK (stock_code ~ '^[0-9]{6}$'),
    corp_name text NOT NULL,
    corp_name_nfc text NOT NULL,
    corp_name_nfd text NOT NULL,
    listed_name text NOT NULL,
    listed_name_nfc text NOT NULL,
    listed_name_nfd text NOT NULL,
    corp_eng_name text,
    market text,
    industry text,
    sector_no smallint,
    sector text,
    listing_date date,
    fiscal_month smallint,
    market_cap bigint,
    n_periodic integer NOT NULL DEFAULT 0,
    n_major integer NOT NULL DEFAULT 0,
    n_exchange integer NOT NULL DEFAULT 0,
    n_holding integer NOT NULL DEFAULT 0,
    note text,
    source_record jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS company_stock_code_uq ON disclosure.company (stock_code);
CREATE INDEX IF NOT EXISTS company_corp_name_nfc_idx ON disclosure.company (corp_name_nfc);
CREATE INDEX IF NOT EXISTS company_corp_name_nfd_idx ON disclosure.company (corp_name_nfd);
CREATE INDEX IF NOT EXISTS company_listed_name_nfc_idx ON disclosure.company (listed_name_nfc);

CREATE TABLE IF NOT EXISTS disclosure.name_alias (
    entity_type text NOT NULL,
    entity_key text NOT NULL,
    name_kind text NOT NULL,
    name_raw text NOT NULL,
    name_nfc text NOT NULL,
    name_nfd text NOT NULL,
    PRIMARY KEY (entity_type, entity_key, name_kind, name_raw)
);
CREATE INDEX IF NOT EXISTS name_alias_nfc_idx ON disclosure.name_alias (name_nfc);
CREATE INDEX IF NOT EXISTS name_alias_nfd_idx ON disclosure.name_alias (name_nfd);

CREATE TABLE IF NOT EXISTS disclosure.disclosure_document (
    doc_id text PRIMARY KEY,
    corp_code text NOT NULL REFERENCES disclosure.company (corp_code),
    corp_name text NOT NULL,
    corp_name_nfc text NOT NULL,
    corp_name_nfd text NOT NULL,
    listed_name text NOT NULL,
    stock_code text NOT NULL,
    industry text,
    sector text,
    doc_group text NOT NULL CHECK (doc_group IN ('periodic', 'major', 'exchange', 'holding')),
    doc_subtype text NOT NULL,
    report_nm text NOT NULL,
    report_nm_nfc text NOT NULL,
    report_nm_nfd text NOT NULL,
    is_correction boolean NOT NULL,
    rcept_no text NOT NULL CHECK (rcept_no ~ '^[0-9]{14}$'),
    rcept_dt date NOT NULL,
    flr_nm text NOT NULL,
    flr_nm_nfc text NOT NULL,
    flr_nm_nfd text NOT NULL,
    base_year smallint,
    base_month smallint,
    file_path text NOT NULL,
    file_path_nfc text NOT NULL,
    file_path_nfd text NOT NULL,
    file_format text NOT NULL,
    n_files integer NOT NULL CHECK (n_files > 0),
    source_record jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (doc_group, rcept_no)
);
CREATE INDEX IF NOT EXISTS disclosure_document_corp_idx
    ON disclosure.disclosure_document (corp_code, rcept_dt);
CREATE INDEX IF NOT EXISTS disclosure_document_receipt_idx
    ON disclosure.disclosure_document (rcept_no);
CREATE INDEX IF NOT EXISTS disclosure_document_report_nm_nfc_idx
    ON disclosure.disclosure_document (report_nm_nfc);
CREATE INDEX IF NOT EXISTS disclosure_document_file_path_nfc_idx
    ON disclosure.disclosure_document (file_path_nfc);

CREATE TABLE IF NOT EXISTS disclosure.source_artifact (
    source_path text PRIMARY KEY,
    source_path_nfc text NOT NULL,
    source_path_nfd text NOT NULL,
    source_path_bytes bytea NOT NULL,
    doc_id text NOT NULL REFERENCES disclosure.disclosure_document (doc_id) ON DELETE CASCADE,
    doc_group text NOT NULL,
    receipt_no text NOT NULL,
    corp_folder text,
    corp_folder_nfc text,
    corp_folder_nfd text,
    receipt_folder text,
    file_name text NOT NULL,
    file_name_nfc text NOT NULL,
    file_name_nfd text NOT NULL,
    file_name_bytes bytea NOT NULL,
    file_role text NOT NULL,
    attachment_code text,
    source_sha256 bytea NOT NULL CHECK (octet_length(source_sha256) = 32),
    source_byte_size bigint NOT NULL CHECK (source_byte_size >= 0),
    detected_format text NOT NULL,
    detected_encoding text,
    declared_encoding text,
    derived_path text NOT NULL,
    derived_sha256 bytea NOT NULL CHECK (octet_length(derived_sha256) = 32),
    derived_byte_size bigint NOT NULL CHECK (derived_byte_size >= 0),
    schema_version text NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS source_artifact_doc_idx ON disclosure.source_artifact (doc_id);
CREATE INDEX IF NOT EXISTS source_artifact_path_nfc_idx
    ON disclosure.source_artifact (source_path_nfc);
CREATE INDEX IF NOT EXISTS source_artifact_corp_folder_nfc_idx
    ON disclosure.source_artifact (corp_folder_nfc);
CREATE INDEX IF NOT EXISTS source_artifact_receipt_idx
    ON disclosure.source_artifact (receipt_no);

CREATE TABLE IF NOT EXISTS disclosure.semantic_ir (
    source_path text PRIMARY KEY REFERENCES disclosure.source_artifact (source_path) ON DELETE CASCADE,
    schema_version text NOT NULL,
    header jsonb NOT NULL,
    projection_contract jsonb NOT NULL,
    diagnostics jsonb NOT NULL,
    section_count integer NOT NULL,
    semantic_field_count integer NOT NULL,
    block_count integer NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS disclosure.semantic_section (
    source_path text NOT NULL REFERENCES disclosure.semantic_ir (source_path) ON DELETE CASCADE,
    section_id text NOT NULL,
    ordinal integer NOT NULL,
    parent_section_id text,
    level integer,
    source_element text,
    title text,
    title_nfc text,
    title_nfd text,
    attributes jsonb NOT NULL,
    start_byte bigint NOT NULL,
    end_byte bigint NOT NULL,
    PRIMARY KEY (source_path, section_id),
    FOREIGN KEY (source_path, parent_section_id)
        REFERENCES disclosure.semantic_section (source_path, section_id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX IF NOT EXISTS semantic_section_title_nfc_idx
    ON disclosure.semantic_section (title_nfc);

CREATE TABLE IF NOT EXISTS disclosure.semantic_field (
    source_path text NOT NULL REFERENCES disclosure.semantic_ir (source_path) ON DELETE CASCADE,
    field_id text NOT NULL,
    ordinal integer NOT NULL,
    section_id text,
    element text NOT NULL,
    key_type text,
    semantic_key text,
    display_text text,
    display_text_nfc text,
    display_text_nfd text,
    machine_value text,
    value_type text NOT NULL,
    attributes jsonb NOT NULL,
    start_byte bigint NOT NULL,
    end_byte bigint NOT NULL,
    PRIMARY KEY (source_path, field_id),
    FOREIGN KEY (source_path, section_id)
        REFERENCES disclosure.semantic_section (source_path, section_id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX IF NOT EXISTS semantic_field_key_idx
    ON disclosure.semantic_field (semantic_key, machine_value);
CREATE INDEX IF NOT EXISTS semantic_field_text_nfc_idx
    ON disclosure.semantic_field (display_text_nfc);

CREATE TABLE IF NOT EXISTS disclosure.semantic_block (
    source_path text NOT NULL REFERENCES disclosure.semantic_ir (source_path) ON DELETE CASCADE,
    block_id text NOT NULL,
    ordinal integer NOT NULL,
    section_id text,
    kind text NOT NULL,
    parent_table_id text,
    text_value text,
    text_value_nfc text,
    text_value_nfd text,
    classification text,
    message text,
    table_class text,
    table_group_class text,
    attributes jsonb NOT NULL,
    start_byte bigint NOT NULL,
    end_byte bigint NOT NULL,
    PRIMARY KEY (source_path, block_id),
    FOREIGN KEY (source_path, section_id)
        REFERENCES disclosure.semantic_section (source_path, section_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (source_path, parent_table_id)
        REFERENCES disclosure.semantic_block (source_path, block_id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX IF NOT EXISTS semantic_block_kind_idx ON disclosure.semantic_block (kind);
CREATE INDEX IF NOT EXISTS semantic_block_text_nfc_idx
    ON disclosure.semantic_block (text_value_nfc);

CREATE TABLE IF NOT EXISTS disclosure.semantic_table_row (
    source_path text NOT NULL,
    block_id text NOT NULL,
    row_index integer NOT NULL,
    start_byte bigint NOT NULL,
    end_byte bigint NOT NULL,
    PRIMARY KEY (source_path, block_id, row_index),
    FOREIGN KEY (source_path, block_id)
        REFERENCES disclosure.semantic_block (source_path, block_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS disclosure.semantic_cell (
    source_path text NOT NULL,
    block_id text NOT NULL,
    row_index integer NOT NULL,
    column_index integer NOT NULL,
    cell_id text NOT NULL,
    rowspan integer NOT NULL,
    colspan integer NOT NULL,
    element text,
    role text NOT NULL,
    semantic_key text,
    machine_value text,
    value_type text NOT NULL,
    display_text text,
    display_text_nfc text,
    display_text_nfd text,
    context_labels text[] NOT NULL,
    context_labels_nfc text[] NOT NULL,
    context_labels_nfd text[] NOT NULL,
    attributes jsonb NOT NULL,
    start_byte bigint NOT NULL,
    end_byte bigint NOT NULL,
    PRIMARY KEY (source_path, block_id, row_index, column_index),
    UNIQUE (source_path, cell_id),
    FOREIGN KEY (source_path, block_id, row_index)
        REFERENCES disclosure.semantic_table_row (source_path, block_id, row_index)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS semantic_cell_key_idx
    ON disclosure.semantic_cell (semantic_key, machine_value);
CREATE INDEX IF NOT EXISTS semantic_cell_text_nfc_idx
    ON disclosure.semantic_cell (display_text_nfc);
CREATE INDEX IF NOT EXISTS semantic_cell_context_labels_nfc_gin
    ON disclosure.semantic_cell USING gin (context_labels_nfc);

CREATE OR REPLACE VIEW disclosure.company_artifact_join AS
SELECT c.corp_code, c.stock_code, c.corp_name, a.source_path, a.receipt_no, a.file_role
FROM disclosure.company AS c
JOIN disclosure.source_artifact AS a ON c.corp_name_nfc = a.corp_folder_nfc;

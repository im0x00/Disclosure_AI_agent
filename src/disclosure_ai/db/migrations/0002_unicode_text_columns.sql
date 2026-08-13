ALTER TABLE disclosure.semantic_field
    ADD COLUMN IF NOT EXISTS display_text_nfd text;

ALTER TABLE disclosure.semantic_block
    ADD COLUMN IF NOT EXISTS text_value_nfd text;

ALTER TABLE disclosure.semantic_cell
    ADD COLUMN IF NOT EXISTS display_text_nfd text,
    ADD COLUMN IF NOT EXISTS context_labels_nfd text[];


-- progress: create_nodes_table
CREATE TABLE IF NOT EXISTS disclosure.nodes (
    node_id uuid PRIMARY KEY,
    document_id text NOT NULL
        REFERENCES disclosure.disclosure_document (doc_id) ON DELETE CASCADE,
    node_type text NOT NULL
        CHECK (node_type IN ('section', 'field', 'block', 'table_row', 'cell')),
    parent_node_id uuid
        REFERENCES disclosure.nodes (node_id) ON DELETE CASCADE
        DEFERRABLE INITIALLY DEFERRED,
    ordinal integer NOT NULL CHECK (ordinal >= 0)
);

-- progress: add_nullable_semantic_node_ids
ALTER TABLE disclosure.semantic_section ADD COLUMN IF NOT EXISTS node_id uuid;
ALTER TABLE disclosure.semantic_field ADD COLUMN IF NOT EXISTS node_id uuid;
ALTER TABLE disclosure.semantic_block ADD COLUMN IF NOT EXISTS node_id uuid;
ALTER TABLE disclosure.semantic_table_row ADD COLUMN IF NOT EXISTS node_id uuid;
ALTER TABLE disclosure.semantic_cell ADD COLUMN IF NOT EXISTS node_id uuid;

-- progress: index_pending_sections
CREATE INDEX IF NOT EXISTS semantic_section_node_pending_idx
    ON disclosure.semantic_section (source_path) WHERE node_id IS NULL;

-- progress-batch: backfill_section_nodes|disclosure.semantic_section|1
WITH batch AS MATERIALIZED (
    SELECT section.ctid AS row_tid,
           md5(section.source_path || chr(31) || 'section' || chr(31) || section.section_id)::uuid
               AS node_id,
           artifact.doc_id AS document_id,
           section.ordinal
    FROM disclosure.semantic_section AS section
    JOIN disclosure.source_artifact AS artifact USING (source_path)
    WHERE section.node_id IS NULL
    ORDER BY section.source_path
    LIMIT 250000
), upserted AS (
    INSERT INTO disclosure.nodes (node_id, document_id, node_type, parent_node_id, ordinal)
    SELECT node_id, document_id, 'section', NULL, ordinal
    FROM batch
    ON CONFLICT (node_id) DO UPDATE SET
        document_id = EXCLUDED.document_id,
        node_type = EXCLUDED.node_type,
        ordinal = EXCLUDED.ordinal
    RETURNING node_id
)
UPDATE disclosure.semantic_section AS section
SET node_id = batch.node_id
FROM batch
JOIN upserted USING (node_id)
WHERE section.ctid = batch.row_tid;

-- progress: drop_pending_section_index
DROP INDEX IF EXISTS disclosure.semantic_section_node_pending_idx;

-- progress: link_section_parents
UPDATE disclosure.nodes AS node
SET parent_node_id =
    md5(section.source_path || chr(31) || 'section' || chr(31)
        || section.parent_section_id)::uuid
FROM disclosure.semantic_section AS section
WHERE node.node_id = section.node_id
  AND section.parent_section_id IS NOT NULL
  AND node.parent_node_id IS DISTINCT FROM
      md5(section.source_path || chr(31) || 'section' || chr(31)
          || section.parent_section_id)::uuid;

-- progress: index_pending_fields
CREATE INDEX IF NOT EXISTS semantic_field_node_pending_idx
    ON disclosure.semantic_field (source_path) WHERE node_id IS NULL;

-- progress-batch: backfill_field_nodes|disclosure.semantic_field|4
WITH batch AS MATERIALIZED (
    SELECT field.ctid AS row_tid,
           md5(field.source_path || chr(31) || 'field' || chr(31) || field.field_id)::uuid
               AS node_id,
           artifact.doc_id AS document_id,
           CASE
               WHEN field.section_id IS NULL THEN NULL
               ELSE md5(field.source_path || chr(31) || 'section' || chr(31)
                         || field.section_id)::uuid
           END AS parent_node_id,
           field.ordinal
    FROM disclosure.semantic_field AS field
    JOIN disclosure.source_artifact AS artifact USING (source_path)
    WHERE field.node_id IS NULL
    ORDER BY field.source_path
    LIMIT 250000
), upserted AS (
    INSERT INTO disclosure.nodes (node_id, document_id, node_type, parent_node_id, ordinal)
    SELECT node_id, document_id, 'field', parent_node_id, ordinal
    FROM batch
    ON CONFLICT (node_id) DO UPDATE SET
        document_id = EXCLUDED.document_id,
        node_type = EXCLUDED.node_type,
        parent_node_id = EXCLUDED.parent_node_id,
        ordinal = EXCLUDED.ordinal
    RETURNING node_id
)
UPDATE disclosure.semantic_field AS field
SET node_id = batch.node_id
FROM batch
JOIN upserted USING (node_id)
WHERE field.ctid = batch.row_tid;

-- progress: drop_pending_field_index
DROP INDEX IF EXISTS disclosure.semantic_field_node_pending_idx;

-- progress: index_pending_blocks
CREATE INDEX IF NOT EXISTS semantic_block_node_pending_idx
    ON disclosure.semantic_block (source_path) WHERE node_id IS NULL;

-- progress-batch: backfill_block_nodes|disclosure.semantic_block|4
WITH batch AS MATERIALIZED (
    SELECT block.ctid AS row_tid,
           md5(block.source_path || chr(31) || 'block' || chr(31) || block.block_id)::uuid
               AS node_id,
           artifact.doc_id AS document_id,
           CASE
               WHEN block.section_id IS NULL THEN NULL
               ELSE md5(block.source_path || chr(31) || 'section' || chr(31)
                         || block.section_id)::uuid
           END AS parent_node_id,
           block.ordinal
    FROM disclosure.semantic_block AS block
    JOIN disclosure.source_artifact AS artifact USING (source_path)
    WHERE block.node_id IS NULL
    ORDER BY block.source_path
    LIMIT 250000
), upserted AS (
    INSERT INTO disclosure.nodes (node_id, document_id, node_type, parent_node_id, ordinal)
    SELECT node_id, document_id, 'block', parent_node_id, ordinal
    FROM batch
    ON CONFLICT (node_id) DO UPDATE SET
        document_id = EXCLUDED.document_id,
        node_type = EXCLUDED.node_type,
        parent_node_id = EXCLUDED.parent_node_id,
        ordinal = EXCLUDED.ordinal
    RETURNING node_id
)
UPDATE disclosure.semantic_block AS block
SET node_id = batch.node_id
FROM batch
JOIN upserted USING (node_id)
WHERE block.ctid = batch.row_tid;

-- progress: drop_pending_block_index
DROP INDEX IF EXISTS disclosure.semantic_block_node_pending_idx;

-- progress: link_nested_block_parents
UPDATE disclosure.nodes AS node
SET parent_node_id =
    md5(block.source_path || chr(31) || 'block' || chr(31)
        || block.parent_table_id)::uuid
FROM disclosure.semantic_block AS block
WHERE node.node_id = block.node_id
  AND block.parent_table_id IS NOT NULL
  AND node.parent_node_id IS DISTINCT FROM
      md5(block.source_path || chr(31) || 'block' || chr(31)
          || block.parent_table_id)::uuid;

-- progress: index_pending_rows
CREATE INDEX IF NOT EXISTS semantic_table_row_node_pending_idx
    ON disclosure.semantic_table_row (source_path) WHERE node_id IS NULL;

-- progress-batch: backfill_row_nodes|disclosure.semantic_table_row|4
WITH batch AS MATERIALIZED (
    SELECT table_row.ctid AS row_tid,
           md5(table_row.source_path || chr(31) || 'table_row' || chr(31)
               || table_row.block_id || ':' || table_row.row_index::text)::uuid AS node_id,
           artifact.doc_id AS document_id,
           md5(table_row.source_path || chr(31) || 'block' || chr(31)
               || table_row.block_id)::uuid AS parent_node_id,
           table_row.row_index AS ordinal
    FROM disclosure.semantic_table_row AS table_row
    JOIN disclosure.source_artifact AS artifact USING (source_path)
    WHERE table_row.node_id IS NULL
    ORDER BY table_row.source_path
    LIMIT 250000
), upserted AS (
    INSERT INTO disclosure.nodes (node_id, document_id, node_type, parent_node_id, ordinal)
    SELECT node_id, document_id, 'table_row', parent_node_id, ordinal
    FROM batch
    ON CONFLICT (node_id) DO UPDATE SET
        document_id = EXCLUDED.document_id,
        node_type = EXCLUDED.node_type,
        parent_node_id = EXCLUDED.parent_node_id,
        ordinal = EXCLUDED.ordinal
    RETURNING node_id
)
UPDATE disclosure.semantic_table_row AS table_row
SET node_id = batch.node_id
FROM batch
JOIN upserted USING (node_id)
WHERE table_row.ctid = batch.row_tid;

-- progress: drop_pending_row_index
DROP INDEX IF EXISTS disclosure.semantic_table_row_node_pending_idx;

-- progress: index_pending_cells
CREATE INDEX IF NOT EXISTS semantic_cell_node_pending_idx
    ON disclosure.semantic_cell (source_path) WHERE node_id IS NULL;

-- progress-batch: backfill_cell_nodes|disclosure.semantic_cell|10
WITH batch AS MATERIALIZED (
    SELECT cell.ctid AS row_tid,
           md5(cell.source_path || chr(31) || 'cell' || chr(31) || cell.cell_id)::uuid
               AS node_id,
           artifact.doc_id AS document_id,
           md5(cell.source_path || chr(31) || 'table_row' || chr(31)
               || cell.block_id || ':' || cell.row_index::text)::uuid AS parent_node_id,
           cell.column_index AS ordinal
    FROM disclosure.semantic_cell AS cell
    JOIN disclosure.source_artifact AS artifact USING (source_path)
    WHERE cell.node_id IS NULL
    ORDER BY cell.source_path
    LIMIT 250000
), upserted AS (
    INSERT INTO disclosure.nodes (node_id, document_id, node_type, parent_node_id, ordinal)
    SELECT node_id, document_id, 'cell', parent_node_id, ordinal
    FROM batch
    ON CONFLICT (node_id) DO UPDATE SET
        document_id = EXCLUDED.document_id,
        node_type = EXCLUDED.node_type,
        parent_node_id = EXCLUDED.parent_node_id,
        ordinal = EXCLUDED.ordinal
    RETURNING node_id
)
UPDATE disclosure.semantic_cell AS cell
SET node_id = batch.node_id
FROM batch
JOIN upserted USING (node_id)
WHERE cell.ctid = batch.row_tid;

-- progress: drop_pending_cell_index
DROP INDEX IF EXISTS disclosure.semantic_cell_node_pending_idx;

-- progress: create_node_lookup_indexes
CREATE INDEX IF NOT EXISTS nodes_document_idx ON disclosure.nodes (document_id);
CREATE INDEX IF NOT EXISTS nodes_parent_idx
    ON disclosure.nodes (parent_node_id, ordinal, node_type, node_id);
CREATE UNIQUE INDEX IF NOT EXISTS semantic_section_node_uq
    ON disclosure.semantic_section (node_id);
CREATE UNIQUE INDEX IF NOT EXISTS semantic_field_node_uq
    ON disclosure.semantic_field (node_id);
CREATE UNIQUE INDEX IF NOT EXISTS semantic_block_node_uq
    ON disclosure.semantic_block (node_id);
CREATE UNIQUE INDEX IF NOT EXISTS semantic_table_row_node_uq
    ON disclosure.semantic_table_row (node_id);
CREATE UNIQUE INDEX IF NOT EXISTS semantic_cell_node_uq
    ON disclosure.semantic_cell (node_id);

-- progress: enforce_section_node_link
ALTER TABLE disclosure.semantic_section ALTER COLUMN node_id SET NOT NULL;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'semantic_section_node_fk'
          AND conrelid = 'disclosure.semantic_section'::regclass
    ) THEN
        ALTER TABLE disclosure.semantic_section
            ADD CONSTRAINT semantic_section_node_fk FOREIGN KEY (node_id)
            REFERENCES disclosure.nodes (node_id) ON DELETE CASCADE NOT VALID;
    END IF;
END
$$;
ALTER TABLE disclosure.semantic_section VALIDATE CONSTRAINT semantic_section_node_fk;

-- progress: enforce_field_node_link
ALTER TABLE disclosure.semantic_field ALTER COLUMN node_id SET NOT NULL;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'semantic_field_node_fk'
          AND conrelid = 'disclosure.semantic_field'::regclass
    ) THEN
        ALTER TABLE disclosure.semantic_field
            ADD CONSTRAINT semantic_field_node_fk FOREIGN KEY (node_id)
            REFERENCES disclosure.nodes (node_id) ON DELETE CASCADE NOT VALID;
    END IF;
END
$$;
ALTER TABLE disclosure.semantic_field VALIDATE CONSTRAINT semantic_field_node_fk;

-- progress: enforce_block_node_link
ALTER TABLE disclosure.semantic_block ALTER COLUMN node_id SET NOT NULL;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'semantic_block_node_fk'
          AND conrelid = 'disclosure.semantic_block'::regclass
    ) THEN
        ALTER TABLE disclosure.semantic_block
            ADD CONSTRAINT semantic_block_node_fk FOREIGN KEY (node_id)
            REFERENCES disclosure.nodes (node_id) ON DELETE CASCADE NOT VALID;
    END IF;
END
$$;
ALTER TABLE disclosure.semantic_block VALIDATE CONSTRAINT semantic_block_node_fk;

-- progress: enforce_row_node_link
ALTER TABLE disclosure.semantic_table_row ALTER COLUMN node_id SET NOT NULL;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'semantic_table_row_node_fk'
          AND conrelid = 'disclosure.semantic_table_row'::regclass
    ) THEN
        ALTER TABLE disclosure.semantic_table_row
            ADD CONSTRAINT semantic_table_row_node_fk FOREIGN KEY (node_id)
            REFERENCES disclosure.nodes (node_id) ON DELETE CASCADE NOT VALID;
    END IF;
END
$$;
ALTER TABLE disclosure.semantic_table_row VALIDATE CONSTRAINT semantic_table_row_node_fk;

-- progress: enforce_cell_node_link
ALTER TABLE disclosure.semantic_cell ALTER COLUMN node_id SET NOT NULL;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'semantic_cell_node_fk'
          AND conrelid = 'disclosure.semantic_cell'::regclass
    ) THEN
        ALTER TABLE disclosure.semantic_cell
            ADD CONSTRAINT semantic_cell_node_fk FOREIGN KEY (node_id)
            REFERENCES disclosure.nodes (node_id) ON DELETE CASCADE NOT VALID;
    END IF;
END
$$;
ALTER TABLE disclosure.semantic_cell VALIDATE CONSTRAINT semantic_cell_node_fk;

-- progress: validate_semantic_node_metadata
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM (
            SELECT section.node_id, section.source_path, 'section'::text AS expected_type
            FROM disclosure.semantic_section AS section
            UNION ALL
            SELECT field.node_id, field.source_path, 'field'
            FROM disclosure.semantic_field AS field
            UNION ALL
            SELECT block.node_id, block.source_path, 'block'
            FROM disclosure.semantic_block AS block
            UNION ALL
            SELECT table_row.node_id, table_row.source_path, 'table_row'
            FROM disclosure.semantic_table_row AS table_row
            UNION ALL
            SELECT cell.node_id, cell.source_path, 'cell'
            FROM disclosure.semantic_cell AS cell
        ) AS semantic
        JOIN disclosure.nodes AS node USING (node_id)
        JOIN disclosure.source_artifact AS artifact USING (source_path)
        WHERE node.node_type <> semantic.expected_type
           OR node.document_id <> artifact.doc_id
        LIMIT 1
    ) THEN
        RAISE EXCEPTION 'semantic node type or document mismatch detected';
    END IF;
END
$$;

-- progress: enforce_node_hierarchy_invariants
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'nodes_no_self_parent'
          AND conrelid = 'disclosure.nodes'::regclass
    ) THEN
        ALTER TABLE disclosure.nodes
            ADD CONSTRAINT nodes_no_self_parent
            CHECK (parent_node_id IS NULL OR parent_node_id <> node_id) NOT VALID;
    END IF;
END
$$;
ALTER TABLE disclosure.nodes VALIDATE CONSTRAINT nodes_no_self_parent;

CREATE OR REPLACE FUNCTION disclosure.validate_node_hierarchy()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    parent_document_id text;
BEGIN
    IF NEW.parent_node_id IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT parent.document_id
    INTO parent_document_id
    FROM disclosure.nodes AS parent
    WHERE parent.node_id = NEW.parent_node_id;

    IF parent_document_id IS DISTINCT FROM NEW.document_id THEN
        RAISE EXCEPTION 'node % and parent % belong to different documents',
            NEW.node_id, NEW.parent_node_id;
    END IF;

    IF EXISTS (
        WITH RECURSIVE ancestors AS (
            SELECT parent.node_id, parent.parent_node_id
            FROM disclosure.nodes AS parent
            WHERE parent.node_id = NEW.parent_node_id
            UNION
            SELECT parent.node_id, parent.parent_node_id
            FROM disclosure.nodes AS parent
            JOIN ancestors AS ancestor ON parent.node_id = ancestor.parent_node_id
        )
        SELECT 1 FROM ancestors WHERE node_id = NEW.node_id
    ) THEN
        RAISE EXCEPTION 'node hierarchy cycle detected at node %', NEW.node_id;
    END IF;

    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS nodes_hierarchy_invariants ON disclosure.nodes;
CREATE CONSTRAINT TRIGGER nodes_hierarchy_invariants
AFTER INSERT OR UPDATE OF node_id, document_id, parent_node_id
ON disclosure.nodes
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION disclosure.validate_node_hierarchy();

-- progress: enforce_semantic_node_metadata
CREATE OR REPLACE FUNCTION disclosure.validate_semantic_node_link()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    actual_node_type text;
    node_document_id text;
    artifact_document_id text;
BEGIN
    SELECT node.node_type, node.document_id
    INTO actual_node_type, node_document_id
    FROM disclosure.nodes AS node
    WHERE node.node_id = NEW.node_id;

    SELECT artifact.doc_id
    INTO artifact_document_id
    FROM disclosure.source_artifact AS artifact
    WHERE artifact.source_path = NEW.source_path;

    IF actual_node_type IS DISTINCT FROM TG_ARGV[0] THEN
        RAISE EXCEPTION 'semantic row expected node type %, got % for node %',
            TG_ARGV[0], actual_node_type, NEW.node_id;
    END IF;
    IF node_document_id IS DISTINCT FROM artifact_document_id THEN
        RAISE EXCEPTION 'semantic row and node % belong to different documents', NEW.node_id;
    END IF;

    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS semantic_section_node_metadata ON disclosure.semantic_section;
CREATE CONSTRAINT TRIGGER semantic_section_node_metadata
AFTER INSERT OR UPDATE OF source_path, node_id ON disclosure.semantic_section
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION disclosure.validate_semantic_node_link('section');

DROP TRIGGER IF EXISTS semantic_field_node_metadata ON disclosure.semantic_field;
CREATE CONSTRAINT TRIGGER semantic_field_node_metadata
AFTER INSERT OR UPDATE OF source_path, node_id ON disclosure.semantic_field
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION disclosure.validate_semantic_node_link('field');

DROP TRIGGER IF EXISTS semantic_block_node_metadata ON disclosure.semantic_block;
CREATE CONSTRAINT TRIGGER semantic_block_node_metadata
AFTER INSERT OR UPDATE OF source_path, node_id ON disclosure.semantic_block
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION disclosure.validate_semantic_node_link('block');

DROP TRIGGER IF EXISTS semantic_table_row_node_metadata ON disclosure.semantic_table_row;
CREATE CONSTRAINT TRIGGER semantic_table_row_node_metadata
AFTER INSERT OR UPDATE OF source_path, node_id ON disclosure.semantic_table_row
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION disclosure.validate_semantic_node_link('table_row');

DROP TRIGGER IF EXISTS semantic_cell_node_metadata ON disclosure.semantic_cell;
CREATE CONSTRAINT TRIGGER semantic_cell_node_metadata
AFTER INSERT OR UPDATE OF source_path, node_id ON disclosure.semantic_cell
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION disclosure.validate_semantic_node_link('cell');

# DisclosureAiAgent

## Local setup

Start the catalog database:

```shell
docker compose up -d postgres
```

Load `universe.csv`, `manifest.jsonl`, and the raw-file registry:

```shell
PYTHONPATH=src uv run python -m evidence.loader
```

The loader executes the SQL files in [`src/sql/`](src/sql/) directly. Raw bytes remain under
`corpus/raw`; PostgreSQL stores their paths, sizes, and SHA-256 values.

Expected catalog counts:

- `company`: 70
- `disclosure_document`: 4,204
- `source_artifact`: 4,622

The 4,622 artifacts are 4,616 XML files plus three PDF and three viewer-HTML fallbacks.

The first `DocumentTree` compiler fixture and corpus-wide contract are documented in
[`docs/document-tree-sample.md`](docs/document-tree-sample.md).

## Validate the whole corpus

This check compiles every manifest document, verifies XML/HTML artifact coverage, hashes,
source byte ranges, raw/display text, and JSON round trips. It reads files only and does not
connect to PostgreSQL.

```shell
PYTHONPATH=src uv run python -m evidence.validate_corpus \
  --report document-tree-validation.json
```

The command uses one fewer worker process than the available logical CPU count by default.
Override it with `--workers N` or `CORPUS_VALIDATION_WORKERS=N`.

Exit code `0` and `"passed": true` mean every document passed. A failure returns exit code `1`
and lists each incompatible `doc_id` in the report.

For the current corpus, a complete pass reports 4,204 manifest/filesystem documents, 4,622
source artifacts, 4,619 expected/compiled tree artifacts, and an empty `failures` list.

## Create the DocumentTree table

Run the catalog loader first so the referenced `corpus.disclosure_document` rows exist. Then
apply only the DocumentTree table SQL from the project root:

```shell
docker compose exec -T postgres sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' \
  < src/sql/007_create_document_tree.sql
```

This creates an empty `corpus.document_tree` table; it does not compile or insert trees.

## Load DocumentTree rows

After corpus validation passes, compile and upsert every tree as JSONB:

```shell
PYTHONPATH=src uv run python -m evidence.document_tree_loader
```

The loader uses one fewer compiler process than the available logical CPU count, keeps a
bounded compile queue full while PostgreSQL writes batches of 50, and runs as one database
transaction. Re-running it updates the same 4,204 rows. Override the pool with `--workers N`
or `DOCUMENT_TREE_LOADER_WORKERS=N`.

The full `DocumentTree` is a provenance/debug representation, not an agent-runtime context.

## Validate agent-runtime grains

Compile and validate every grain without writing to PostgreSQL:

```shell
PYTHONPATH=src uv run python -m evidence.validate_grains \
  --workers 8 \
  --max-estimated-tokens 1800 \
  --report grain-validation.json
```

The process pool independently checks content/context source coverage, empty table cells and
column positions, deterministic IDs and neighbor links, exact UTF-8 byte ranges, token limits,
and JSON round trips. Run the loader only after exit code `0` and `"passed": true`.

## Load agent-runtime grains

Compile compact semantic grains directly from the corpus and upsert them without storing the
full tree JSON:

```shell
PYTHONPATH=src uv run python -m evidence.document_grain_loader \
  --workers 8 \
  --document-batch-size 10 \
  --max-estimated-tokens 1800
```

Each grain keeps non-overlapping core text, repeated heading/table context, exact source byte
ranges, stable ordering, and previous/next links. Table rows keep empty cell positions,
row/column indexes, and spans. Source attributes are not copied into grain context; exact source
ranges allow later relation or metadata builders to read them from the DocumentTree. The loader uses a bounded process pool,
retries interrupted filesystem calls, removes stale grains for each recompiled document, and
commits each document batch so a long interrupted run can be resumed safely. The corpus catalog
must be loaded first because grain rows reference `corpus.disclosure_document` and
`corpus.source_artifact`.

## Build and load document relations

Intent: build and inspect one complete edge snapshot before changing the database.

Build from the current database JSONB so the snapshot uses the exact loaded trees and grain IDs:

```shell
PYTHONPATH=src uv run python -m evidence.relation_builder \
  --from-database \
  --database-url "$DATABASE_URL" \
  --manual-reviews docs/relation-review/correction-comparisons.jsonl \
  --output-dir outputs/relations
```

This writes `outputs/relations/relations.jsonl` and
`outputs/relations/unresolved.jsonl`; it does not connect to PostgreSQL. Inspect those files,
then atomically replace the database snapshot:

```shell
PYTHONPATH=src uv run python -m evidence.document_relation_loader \
  --relations-path outputs/relations/relations.jsonl \
  --unresolved-path outputs/relations/unresolved.jsonl \
  --database-url "$DATABASE_URL" \
  --replace
```

The catalog and grain loaders must run first. The relation loader validates every non-empty
grain endpoint against `corpus.document_grain` inside the same transaction. Any missing or
wrong-document grain rolls back the full replacement. The loader rejects
`ambiguous_candidates`; `no_in_corpus_candidate` and manually checked `reviewed_no_match`
remain audit-only and are never inserted as edges.


## Boundaries

# PostgreSQL loader

The loader has two independent phases so pre-existing structured data can be loaded while semantic
IR derivation is still running.

## Data scope

`structured` loads:

- `corpus/universe.csv` into `disclosure.company` and `disclosure.name_alias`;
- `corpus/manifest.jsonl` into `disclosure.disclosure_document`.

`universe.xlsx` is the viewing copy of `universe.csv`, so it is not loaded twice. `data_filter.md`
is documentation. `semantics/*.yaml` is intentionally outside this loader.

`derived` loads the completed Semantic Structural IR into:

- `source_artifact` and `semantic_ir`;
- `semantic_section` and `semantic_field`;
- `semantic_block`, `semantic_table_row`, and `semantic_cell`.

## Unicode join contract

Raw values are always retained. Joinable names, titles, text, file names, and paths additionally
store NFC and NFD forms. Filesystem bytes are retained as `bytea` for source paths and file names.

For example, macOS NFD company folders join to NFC company master names through:

```sql
SELECT * FROM disclosure.company_artifact_join;
```

Equivalent explicit join:

```sql
SELECT c.corp_code, c.corp_name, a.source_path
FROM disclosure.company AS c
JOIN disclosure.source_artifact AS a
  ON c.corp_name_nfc = a.corp_folder_nfc;
```

Application input should be normalized to NFC before querying `*_nfc`, or PostgreSQL 17 can do it:

```sql
SELECT source_path, title
FROM disclosure.semantic_section
WHERE title_nfc = normalize(%s, NFC);
```

## Safety and idempotency

- Migrations and structured upserts are idempotent.
- Derived artifacts load one transaction at a time.
- A rerun skips rows whose derived SHA-256 is already current.
- The loader verifies `_SUCCESS.json`, every derived file's size/SHA-256, its source SHA-256 link,
  lossless parsing, and full non-whitespace text coverage.
- It refuses an active/incomplete derived tree before scanning its group directories.

## Commands

Start PostgreSQL:

```shell
docker compose up -d postgres
```

Load the existing structured datasets now, even while derivation is running:

```shell
PYTHONPATH=src uv run python -m disclosure_ai.db structured corpus
```

After derivation creates `_SUCCESS.json`, load Semantic Structural IR:

```shell
PYTHONPATH=src uv run python -m disclosure_ai.db derived corpus
```

On a fresh database after derivation is complete, both phases can run together:

```shell
PYTHONPATH=src uv run python -m disclosure_ai.db all corpus
```

`DATABASE_URL` is read from the environment. Without it, the CLI uses the local values from
`compose.yaml`. `--database-url` overrides it; `--force` reloads unchanged derived artifacts.

## Query examples

DART semantic keys:

```sql
SELECT d.corp_name, d.report_nm, f.semantic_key, f.display_text, f.machine_value
FROM disclosure.semantic_field AS f
JOIN disclosure.source_artifact AS a USING (source_path)
JOIN disclosure.disclosure_document AS d ON d.doc_id = a.doc_id
WHERE f.semantic_key = 'RPT_RSP_DT';
```

Human-readable table values with their label context:

```sql
SELECT d.report_nm, c.context_labels, c.display_text, c.machine_value
FROM disclosure.semantic_cell AS c
JOIN disclosure.source_artifact AS a USING (source_path)
JOIN disclosure.disclosure_document AS d ON d.doc_id = a.doc_id
WHERE c.role = 'value';
```

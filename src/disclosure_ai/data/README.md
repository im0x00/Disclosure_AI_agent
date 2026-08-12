# Lossless disclosure data

This package treats the source byte stream and its filesystem path as the source of truth.
Parsing creates derived tokens and a recovered concrete syntax tree; it never rewrites the raw
artifact.

## Guarantees

- The original bytes, SHA-256, byte size, raw path bytes, raw path components, and file name are
  retained in `SourceArtifact` and `SourceEnvelope`.
- NFC text is an additional join key. It never replaces the filesystem spelling (macOS paths in
  this corpus are NFD while `universe.csv` company names are NFC).
- Token spans are contiguous, non-overlapping, and cover every source byte exactly once.
- `ParsedArtifact.assert_lossless()` fails if concatenating token spans does not recreate the
  source bytes exactly.
- Malformed markup is not edited. Tree recovery is recorded as `RecoveryEvent` values.
- Derived descriptor values retain their original bytes and byte offsets.

## Format routing

- `periodic`, `major`, and `holding`: tolerant DART markup tokenization. Only ASCII-uppercase DART
  tag names are structural, so narrative text such as `<현금흐름위험회피>` remains text.
- `exchange`: tolerant HTML tokenization even though files use an `.xml` suffix.
- JSON, PDF, and unknown files: one raw token spanning the entire artifact.

## Use

```python
from disclosure_ai.data import CorpusCatalog, describe, parse_artifact

catalog = CorpusCatalog("corpus")
document = catalog.read_document("periodic", "20240318000916")

for source in document.artifacts:
    parsed = parse_artifact(source)
    parsed.assert_lossless()
    descriptor = describe(parsed)
```

Verify every raw artifact, including `list_*.json` sidecars and PDF/HTML fallbacks:

```shell
PYTHONPATH=src uv run python -m disclosure_ai.data corpus
```

## Semantic structural IR

Materialization writes one JSON artifact per disclosure source file under a mirrored directory:

```text
corpus/derived/semantic-structural-ir-v1/
├── periodic/<corp>/<receipt-folder>/<source-name>.semantic.json[.gz]
├── major/<corp>/<receipt-folder>/<source-name>.semantic.json[.gz]
├── exchange/<corp>/<receipt-folder>/<source-name>.semantic.json[.gz]
├── holding/<corp>/<receipt-folder>/<source-name>.semantic.json[.gz]
├── manifest.jsonl
├── _RUN.json
└── _SUCCESS.json   # written only after an unfiltered complete run
```

Each artifact contains:

- exact source identity: raw path and path bytes, SHA-256, byte size, file role, encoding;
- unchanged document-level metadata from `corpus/manifest.jsonl`;
- document header and section hierarchy;
- ordered headings, paragraphs, tables, rows, and grid-positioned cells;
- `ACODE`/`AUNIT` semantic fields with display text and machine values;
- inferred cell label context, conservative value types, and source byte evidence spans;
- parser recovery diagnostics and explicit `unmapped_text` blocks;
- a coverage assertion showing that every non-whitespace source text node was mapped.

The IR is an evidence-linked projection, not a replacement for `corpus/raw`. Exact reconstruction
uses the retained source path plus SHA-256 and byte spans. Presentation-only attributes such as
width and alignment are omitted from the projection but remain in the immutable raw source.

Run one receipt first:

```shell
PYTHONPATH=src uv run python -m disclosure_ai.data.derive corpus \
  --receipt 20250325800001 --pretty
```

Then materialize the complete corpus as compact deterministic gzip JSON. Compression is recommended
because evidence-linked JSON is several times larger than the source before compression:

```shell
PYTHONPATH=src uv run python -m disclosure_ai.data.derive corpus --gzip
```

The writer uses atomic replacement. Rerunning resumes by skipping artifacts whose schema version
and source SHA-256 are already current. Use `--force` to rebuild, `--group exchange` to select a
group, `--pretty` for larger indented JSON, or `--fsync` for slower power-loss durability. Keep the
same compression mode when resuming a run.

After a complete run, load the materialization and the pre-existing structured corpus datasets into
PostgreSQL using the commands in [`../db/README.md`](../db/README.md). The database loader refuses
this directory until `_SUCCESS.json` exists.

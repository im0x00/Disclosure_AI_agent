# Correction relation manual review

`correction-comparisons.jsonl` stores cases where deterministic receipt/date matching could not select one target safely. The stored reading decision selects the target document; content similarity never creates an edge or a grain endpoint.

Each line records:

- `source_doc_id`: correction filing
- `candidate_doc_ids`: the exact candidate set seen during review
- `selected_target_doc_id`: the immediately preceding version selected by reading the filings, or `null` when no candidate matches
- `rationale` and `evidence`: the comparison that supports the choice

The resolver applies a review only when its current candidate set exactly matches the stored set. A corpus rebuild that adds or removes a candidate therefore leaves the edge unresolved until the case is reviewed again.

Reviewed cases: 105 (102 selected, 3 abstained). These records were produced by reading the current corpus, not by an LLM runtime call.

Build and load the complete edge snapshot:

```bash
PYTHONPATH=src uv run python -m evidence.relation_builder \
  --from-database \
  --database-url "$DATABASE_URL" \
  --manual-reviews docs/relation-review/correction-comparisons.jsonl \
  --output-dir outputs/relations

PYTHONPATH=src uv run python -m evidence.document_relation_loader \
  --relations-path outputs/relations/relations.jsonl \
  --unresolved-path outputs/relations/unresolved.jsonl \
  --database-url "$DATABASE_URL" \
  --replace
```

The loader requires the catalog and `document_grain` rows to exist first. It replaces the
edge snapshot in one transaction and rolls back when a grain endpoint is missing or belongs
to another document. `unresolved.jsonl` remains file-backed and is not inserted as an edge.

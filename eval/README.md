# Evaluation data

`eval/` is the version-controlled source of truth for benchmark data. Raw corpus files are
not copied here; evidence records point to immutable source paths, hashes, and byte ranges.

## Files

- `REVIEW.md`: human-readable review queue; reviewers judge task meaning here.
- `REVIEW_BATCH_01.md`: human-readable review table for the initial development expansion.
- `REVIEW_MINI_WORLD_V1.md`: every mini-world question with its expected answer, axes,
  and required documents.
- `axis_definitions.json`: extensible axis registry and core capability matrix.
- `mini_world.json`: the development-world boundary and relation-closure policy.
- `mini_world_suite.json`: the exact reusable and new case IDs in the mini-world suite.
- `oracles.jsonl`: one independently verified source cluster per line, including its entities,
  facts, exact evidence, and verification records.
- `cases/facility_investment_pilot.jsonl`: one complete case per line, including its question,
  logical query, axes, oracle references, required documents, and grading contract.
- `cases/open_core_pilot.jsonl`: open-response cases for the two remaining core matrix cells.
- `cases/development_batch_01.jsonl`: capability-balanced initial-development cases.
- `cases/mini_world_v1.jsonl`: mini-world-specific additions; reusable older cases are
  referenced by `mini_world_suite.json` rather than duplicated.
- `cases/seed.json`: existing self-contained seed cases.

## Lifecycle

`candidate -> fact_verified -> query_accepted -> released`

Facts in the facility-investment pilot are `fact_verified`. Logical queries and questions
remain `candidate` until their intended meaning is reviewed.

## Evidence semantics

- Grain-level retrieval mapping is deferred until the retrieval contract is defined.
- Existing `required_grain_ids` in the first pilot are preserved only as dormant metadata;
  they are not part of the current grading contract.
- New cases stop at `required_document_ids` and raw evidence anchors.
- `oracle_evidence_ids` grade fact extraction and provenance at exact raw-row level.
- A grain may intentionally contain an entire disclosure form. Exact source ranges do not
  imply that retrieval should return cell-sized chunks.

## Evaluation axes

- company identity and cardinality
- period identity and cardinality
- required-document cardinality
- document type
- operation
- response mode (`closed` or `open`)
- scope
- version policy
- answerability

Event-specific attributes such as an investment target are entity attributes, not axes.

Every complete case must contain every axis listed in `axis_definitions.json` under
`required_case_axes`. New axes and values may be appended without rewriting existing records;
the axis-registry schema version records taxonomy changes.

Cases derived from the same source facts reference the same `oracle_cluster_id` in
`oracles.jsonl`. Question variants and minimal pairs within one cluster do not count as
independent benchmark samples.

## Mini-world suite

`development-mini-v1` contains 43 cases across 9 independent oracle clusters. It reuses
15 existing cases and adds 28 cases without copying case IDs. All required documents must
resolve inside the mini world after its configured relation closure. The embedding index
scope is derived from the suite's selected case IDs and their `required_document_ids`, then
expanded by the world relation policy. Adding a company to the world does not implicitly
index every disclosure from that company. Every grain from each resolved document is kept.

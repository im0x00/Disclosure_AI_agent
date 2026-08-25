# Disclosure modeling review

## Decision

Keep one shared `DocumentTree`. Do not create a different tree schema for every
`doc_subtype`.

The current tree is the source-preservation layer: it keeps document order, tags,
attributes, text, tables, and source ranges. That is enough for rendering, source citation,
and later reprocessing. It is not enough for normalized comparison, event linking, or
point-in-time answers.

Add semantic projections above the tree:

```text
RawArtifact -> DocumentTree -> SemanticProjection -> Relation / Timeline
```

- `DocumentTree`: one common, lossless structural contract.
- `SemanticProjection`: common envelope plus subtype-specific payload.
- `Relation`: correction, termination, and other cross-document links.
- `Timeline`: filing time and the time described by a filing.

## What is and is not currently classified

The compiler handles every current document shape, but the manifest taxonomy is not
complete:

- The eight populated subtypes cover `periodic`, `exchange`, and `holding`.
- All 598 `major` filings have an empty `doc_subtype`.
- Those 598 filings contain 29 normalized `report_nm` labels before further alias merging.

Therefore, “all documents compile into the tree” is true. “All documents have a useful
semantic subtype” is false.

## Recommended semantic projections

| Family | Projection | Important normalized fields |
|---|---|---|
| annual / half / quarter | `PeriodicReport` | period, duration, consolidated/separate scope, concept, value, unit, dimensions |
| contract signed | `SupplyContractEvent` | counterparty, contract name, amount, revenue ratio, start/end date, region, disclosure status |
| contract terminated | `SupplyContractTerminationEvent` | terminated contract, amount, reason, termination date |
| facility investment | `FacilityInvestmentEvent` | target, amount, equity ratio, purpose, start/end date, decision date |
| material management matter | `MaterialManagementEvent` | topic, lifecycle stage, product/asset, counterparty, regulator, dates, amounts |
| large holding | `LargeHoldingReport` | issuer, reporter, related parties, before/after shares and ratio, purpose, change reason |

Use subtype-specific field maps, validators, and extraction tests. Do not duplicate the
tree parser. Keep provenance from every semantic field back to one or more tree source
ranges.

`투자판단관련주요경영사항` needs a second-level `topic` because the current subtype includes
clinical trials, approvals, license contracts, milestone payments, supply arrangements,
and other unrelated events.

## Corrections and time

Treat a correction as a relation, not as a new subtype. Keep `is_correction` as a derived,
indexed convenience flag.

Suggested relation model:

```text
DocumentVersion --amends--> DocumentVersion
DocumentVersion --belongs_to--> DisclosureSeries
ContractTerminationEvent --terminates--> SupplyContractEvent
```

Do not combine `amends` and `terminates`. A corrected filing changes a prior filing version;
a contract-termination filing changes the state of the reported business event.

Track two time axes:

- filing time: when this version became available (`receipt_date`, and receipt time when
  available);
- subject time: reporting period, decision date, contract period, holding reference date,
  or other time described by the filing.

For an “as known on date X” query, select the newest version filed on or before X. For a
business-event query, use subject time while retaining the filing-time cutoff.

Do not infer correction targets from date alone. Use issuer, form/subtype, period or event
identity, the correction wrapper's referenced submission date, and related-disclosure
evidence. Preserve an unresolved external target when the original filing is outside the
corpus.

Corpus evidence supports this caution:

- 1,004 filings have `is_correction=true`.
- 1,001 raw filings expose a parseable referenced submission date with a simple scan.
- A coarse in-corpus match by issuer, group/subtype, period, and referenced date leaves 341
  without a target and 84 with multiple candidates.

These match counts are diagnostic, not production linking rules. They show why the edge
needs evidence and a resolution status instead of a date-only foreign key.

## Implementation boundary

The next implementation should add semantic output beside `DocumentTree`, not change
`DocumentTree` 1.0. A practical order is:

1. define the common semantic envelope and provenance contract;
2. implement the four structured exchange forms and large-holding form;
3. implement periodic facts with period/unit/scope semantics;
4. add correction-series resolution with unresolved targets;
5. derive `major` subtypes from form code/report name, then add projections by frequency.

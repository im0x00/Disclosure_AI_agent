# Representative `doc_subtype` samples

## Selection rule

Each example is a non-correction filing whose primary source byte size is closest to the
median for that subtype. This avoids choosing only unusually small or convenient files.
The examples remain immutable under `corpus/raw`; this document provides one review point
under `docs` and links to the source.

| `doc_subtype` | Original / correction count | Representative filing | Primary bytes |
|---|---:|---|---:|
| `annual` | 207 / 84 | `periodic_20260318001622` | 5,814,530 |
| `half` | 206 / 28 | `periodic_20230814002141` | 3,539,406 |
| `quarter` | 482 / 47 | `periodic_20231114002308` | 2,970,501 |
| `단일판매공급계약체결` | 543 / 563 | `exchange_20241231800107` | 8,074 |
| `단일판매공급계약해지` | 20 / 0 | `exchange_20240603800359` | 9,054 |
| `신규시설투자등` | 28 / 15 | `exchange_20240220800842` | 8,337 |
| `투자판단관련주요경영사항` | 247 / 53 | `exchange_20230801800563` | 8,786 |
| `대량보유상황보고서` | 1,042 / 41 | `holding_20240416000451` | 110,526 |

Counts are document counts, so a source filing may have more than one correction.

## `annual`

- Company/report: 에코프로비엠, `사업보고서 (2025.12)`
- Source: [20260318001622.xml](../corpus/raw/periodic/에코프로비엠/20260318001622_annual_2025_12/20260318001622.xml)
- Additional artifacts: [separate audit report](../corpus/raw/periodic/에코프로비엠/20260318001622_annual_2025_12/20260318001622_00760.xml), [consolidated audit report](../corpus/raw/periodic/에코프로비엠/20260318001622_annual_2025_12/20260318001622_00761.xml)
- Tree shape: 3 artifacts; the primary source contains 46,204 nodes.
- Visible outline: company overview, business, financial statements, notes, governance,
  shareholders, executives, affiliates, and related-party matters.
- Semantic issue: the same table structure can contain facts with different period, unit,
  consolidation scope, accounting concept, and dimensions. Those meanings cannot be
  recovered from `Node.kind=table_cell` alone.

## `half`

- Company/report: POSCO홀딩스, `반기보고서 (2023.06)`
- Source: [20230814002141.xml](../corpus/raw/periodic/POSCO홀딩스/20230814002141_half_2023_06/20230814002141.xml)
- Tree shape: 1 artifact, 48,856 nodes.
- Visible outline: mostly the same top-level sections as an annual report, with a six-month
  reporting period and interim financial statements.
- Semantic issue: `annual`, `half`, and `quarter` should share one periodic projection. The
  reporting period and duration distinguish them; separate tree schemas would duplicate
  almost all structure.

## `quarter`

- Company/report: 대우건설, `분기보고서 (2023.09)`
- Source: [20231114002308.xml](../corpus/raw/periodic/대우건설/20231114002308_quarter_2023_09/20231114002308.xml)
- Tree shape: 1 artifact, 38,802 nodes.
- Visible outline: the same broad company/business/financial sections, with a nine-month
  reporting endpoint in this example.
- Semantic issue: “quarter” in the form name does not imply every value covers three months.
  Balance-sheet facts are instant facts; income and cash-flow facts may be quarter-to-date
  or year-to-date. Each extracted fact needs its own period.

## `단일판매공급계약체결`

- Company/report: 현대글로비스, `단일판매ㆍ공급계약체결`
- Source: [20241231800107.xml](../corpus/raw/exchange/현대글로비스/20241231800107/20241231800107.xml)
- Tree shape: 1 table, 19 rows, 40 cells.
- Example values: completed-vehicle sea transport; KRW 3.334 trillion; Kia; 13.0% of recent
  revenue; contract period 2025-01-01 through 2029-12-31.
- Semantic issue: these are stable named fields and should become a typed contract event.
  Amount, currency, ratio denominator, counterparty, and contract dates need normalized
  types while retaining their source cells.

## `단일판매공급계약해지`

- Company/report: 두산퓨얼셀, `단일판매ㆍ공급계약해지`
- Source: [20240603800359.xml](../corpus/raw/exchange/두산퓨얼셀/20240603800359/20240603800359.xml)
- Tree shape: 1 table, 16 rows, 35 cells.
- Example values: fuel-cell system supply contract; KRW 19.3 billion; termination date
  2024-05-31; customer failure to satisfy activation conditions.
- Semantic issue: this document is both an event and a relation. Create a termination event
  and link it with `terminates` to the earlier contract event. Do not use the correction
  relation for this link.

## `신규시설투자등`

- Company/report: LG이노텍, `신규시설투자등`
- Source: [20240220800842.xml](../corpus/raw/exchange/LG이노텍/20240220800842/20240220800842.xml)
- Tree shape: 1 table, 17 rows, 38 cells.
- Example values: optical-solutions facility investment; KRW 383 billion; 9.0% of equity;
  2024-02-20 through 2024-12-31; decision date 2024-02-20.
- Semantic issue: distinguish the decision date, investment execution period, amount,
  denominator basis date, and purpose. They are different temporal and numeric roles.

## `투자판단관련주요경영사항`

- Company/report: 한미약품, `투자판단관련주요경영사항`
- Source: [20230801800563.xml](../corpus/raw/exchange/한미약품/20230801800563/20230801800563.xml)
- Tree shape: 2 tables, 12 rows, 23 cells.
- Example topic: change of counterparty for a Rolvedon/Rolontis license agreement after an
  acquisition.
- Semantic issue: this subtype is only a disclosure form category. It needs a second-level
  topic and topic-specific payload; a clinical approval, license transfer, milestone
  receipt, and supply arrangement should not produce the same semantic object.

## `대량보유상황보고서`

- Company/report: 현대글로비스, `주식등의대량보유상황보고서(일반)`
- Source: [20240416000451.xml](../corpus/raw/holding/현대글로비스/20240416000451/20240416000451.xml)
- Tree shape: 32 tables, 154 rows, 871 cells.
- Example values: reporter 정의선; before/after holdings 18,880,348 / 18,881,748 shares;
  50.35% / 50.35%; reason is a related-party and share-count change.
- Semantic issue: model issuer, reporter, related parties, security type, ownership form,
  contracts, purpose, and before/after snapshots explicitly. A single generic table fact
  loses actor roles and the meaning of the change.

## Correction example

The correction wrapper and the corrected full document coexist in one tree. For example,
[exchange_20250731800028](../corpus/raw/exchange/삼성전자/20250731800028/20250731800028.xml)
contains a correction table referencing the 2025-07-28 submission and the corrected supply
contract form. The corrected counterparty changes from a confidential generic label to
Tesla.

This supports keeping the wrapper in `DocumentTree`, extracting correction metadata into a
semantic projection, and resolving an `amends` edge separately.

## Classification gap outside these eight subtypes

`major` is not represented above because its 598 manifest rows currently have an empty
`doc_subtype`. The report names cover 29 normalized labels such as treasury-share
acquisition/disposal, capital increases, mergers, demergers, convertible bonds, asset
transfers, and litigation. This group needs subtype normalization before it can receive the
same representative-sample treatment.

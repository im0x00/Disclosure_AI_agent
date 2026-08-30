# Eval review

이 파일만 사람이 읽습니다. JSONL은 runtime용입니다.

검수자는 raw 숫자를 다시 뽑지 않습니다. 다음 한 가지만 판단합니다.

> 이 질문과 정답 범위가 실제 agent capability를 제대로 test하는가?

결과를 알려줄 때는 `001 accept`, `002 reject: 이유`처럼 case ID와 판단만 적으면 됩니다.

## 지금 판단할 두 case

### open-core:001 — single document summary

- **Question:** SK하이닉스의 2026년 1분기 분기보고서에 나온 투자집행 현황을 투자 유형, 대상 자산, 투자 효과, 투자 기간, 누적 투자액 기준으로 정리해줘.
- **Test:** 한 document에서 정해진 section을 찾고 여러 field를 빠짐없이 extract하여 summary하는가.
- **Expected answer outline:** 보완투자 등 / 기계장치 외 / 생산능력증가 등 / 2026-01-01~2026-03-31 / 7,348십억원(7.348조원) 누적실적.
- **Must not say:** 7,348억원 또는 future investment plan.
- **당신의 판단:** `누적 투자집행 현황`이 search-and-extraction/open의 기초 case로 적절한가?
- [x] accept — 2026-08-28
- [ ] reject

### open-core:002 — multiple document fundraising aggregation

- **Question:** 우리기술이 2025년에 공시한 자금조달 결정을 유형별(유상증자, CB, BW, EB)로 정리하고, 각 공시의 금액과 자금 목적 및 유형별 합계를 알려줘.
- **Test:** 같은 회사의 2025년 fundraising decision을 전부 retrieve하고 type별로 분류·합산하는가.
- **Expected answer outline:**
  - 유상증자 0건
  - CB 3건, 합계 378억원
  - 17회: 50억원, 운영자금
  - 18회: 108억원, 운영자금
  - 19회: 220억원, 운영자금 60억원 + 채무상환 160억원
  - BW 0건, EB 0건
- **Excluded:** 2025-08-18 제3자 CB call-option 행사. 신규 fundraising decision이 아니기 때문.
- **당신의 판단:** `filed-year + instrument type + 신규 조달 결정`이라는 scope가 실제 multi-retrieval/open case로 적절한가?
- [x] accept — 2026-08-28
- [ ] reject

---

## 이미 만든 closed/history pilot

### facility:001 — fact lookup

- **Question:** 한화오션의 2025-04-28 Floating Dock 확장 투자금액은?
- **Expected:** 3,328억원.
- **Test:** single document exact lookup.
- [ ] accept
- [ ] reject

### facility:002 — sum

- **Question:** 한화오션이 2025-04-28 결정한 신규시설투자 2건의 합계는?
- **Expected:** 6,008억원.
- **Test:** two-document retrieval + sum.
- [ ] accept
- [ ] reject

### facility:003 — company comparison

- **Question:** 한화오션과 LG유플러스의 2025년 신규시설투자 합계 중 어느 회사가 크며 차이는?
- **Expected:** LG유플러스가 148억원 큼.
- **Test:** multi-company retrieval + per-company sum + comparison.
- [ ] accept
- [ ] reject

### facility:004 — as-of correction lookup

- **Question:** 2025-06-01 당시 레인보우로보틱스 투자금액은?
- **Expected:** 281억 7,842만원.
- **Test:** requested date에 유효했던 correction version 선택.
- [ ] accept
- [ ] reject

### facility:005 — correction history

- **Question:** 투자금액과 종료일이 correction series에서 어떻게 바뀌었는가?
- **Expected outline:** 278.5억원 → 281.7842억원 → 285.3352억원; 종료일 2025-12-15 → 2026-03-31 → 2026-03-27.
- **Test:** four documents를 시간순으로 연결하여 change history summary.
- [ ] accept
- [ ] reject

### facility:006 — percentage change

- **Question:** 최초 대비 2026-03-31 기준 투자금액은 얼마와 몇 % 증가했는가?
- **Expected:** 6억 8,352만원, 약 2.454291%.
- **Test:** original/latest version retrieval + exact calculation.
- [ ] accept
- [ ] reject

### facility:007 — unanswerable

- **Question:** 2026년 5월 final settlement 뒤 확정된 투자금액은?
- **Expected:** corpus가 2026-03-31에 끝나므로 알 수 없음.
- **Test:** 비슷한 최신 금액을 답으로 만들지 않고 abstain하는가.
- [ ] accept
- [ ] reject

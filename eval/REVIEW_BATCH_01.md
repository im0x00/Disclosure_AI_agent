# Development batch 01 review

이 파일만 사람이 봅니다. Raw fact, hash, byte range, 계산은 verification을 마쳤습니다.

위 table은 index입니다. 실제 검수 대상인 122개 Question과 Expected answer는 아래 `Actual case review` section에 모두 있습니다.

| Oracle cluster | Test | Source scope | Expected boundary |
|---|---|---|---|
| `cluster:dev:contract:exchange_20250728800035` | lookup/date/ratio/negative/open summary | 삼성전자 / 반도체 위탁생산 공급계약 | amount=22,764,764,160,000; end=2033-12-31; ratio=7.6; realized revenue=unanswerable |
| `cluster:dev:contract:exchange_20250114800153` | lookup/date/ratio/negative/open summary | 한미반도체 / HBM 제조용 장비 수주 | amount=10,807,500,000; end=2025-07-01; ratio=6.80; realized revenue=unanswerable |
| `cluster:dev:contract:exchange_20250731800497` | single contract lookup | 현대오토에버 / hCloud 서비스 제공 계약 | amount=125,514,000,000; end=2030-06-30; ratio=3.4; realized revenue=unanswerable |
| `cluster:dev:contract:exchange_20250623800158` | single contract lookup | LG씨엔에스 / 죽전 데이터센터 Co-location 서비스 계약서 | amount=-; end=2033-05-31; ratio=-; realized revenue=unanswerable |
| `cluster:dev:contract:exchange_20250114800022` | single contract lookup | 삼성바이오로직스 / 의약품 위탁생산계약 | amount=2,074,694,843,000; end=2030-12-31; ratio=56.15; realized revenue=unanswerable |
| `cluster:dev:contract:exchange_20250326800989` | single contract lookup | 한국항공우주 / 소형무장헬기 2차양산 기체 PBL 사업 | amount=112,893,000,000; end=2028-03-24; ratio=3.0; realized revenue=unanswerable |
| `cluster:dev:contract:exchange_20250210801035` | single contract lookup | 한화오션 / LNGC 2척 | amount=732,200,000,000; end=2027-09-30; ratio=9.9; realized revenue=unanswerable |
| `cluster:dev:contract:exchange_20250226800006` | single contract lookup | 현대로템 / 모로코 철도청 전동차 사업 | amount=2,202,726,004,050; end=2034-01-25; ratio=61.4; realized revenue=unanswerable |
| `cluster:dev:contract:exchange_20250123800036` | single contract lookup | HD현대중공업 / 초대형 컨테이너선 12척 | amount=3,716,000,000,000; end=2028-12-29; ratio=31.06; realized revenue=unanswerable |
| `cluster:dev:contract:exchange_20250313800043` | single contract lookup | 두산에너빌리티 / Rumah #1 IPP | amount=1,128,260,775,513; end=2028-05-31; ratio=6.41; realized revenue=unanswerable |
| `cluster:dev:contract:exchange_20250318800092` | single contract lookup | 엘에스일렉트릭 / Big Tech Data Center PJT | amount=162,527,055,440; end=2025-10-27; ratio=3.8; realized revenue=unanswerable |
| `cluster:dev:contract:exchange_20250616800147` | single contract lookup | LG에너지솔루션 / 전기차 배터리 공급계약 | amount=-; end=2030-12-31; ratio=-; realized revenue=unanswerable |
| `cluster:dev:contracts:00164478:2025q1` | count/sum/ranking/difference/open/negative | 현대건설 / 2025 Q1 / 2 docs | count=2; total=2814485600000; max=가양동 CJ부지 업무복합시설 신축공사 |
| `cluster:dev:contracts:00124540:2025q1` | count/sum/ranking/difference/open/negative | 대우건설 / 2025 Q1 / 3 docs | count=3; total=1638691456115; max=개포주공5단지아파트 재건축정비사업 |
| `cluster:dev:contracts:00126308:2025q1` | multi-contract count/sum/ranking/open | 삼성E&A / 2025 Q1 / 3 docs | count=3; total=3815056116698; max=UAE Methanol Project |
| `cluster:dev:contracts:00503668:2025q2` | multi-contract count/sum/ranking/open | LIG디펜스앤에어로스페이스 / 2025 Q2 / 5 docs | count=5; total=724229000000; max=정지궤도 기상.우주기상 위성 시스템 및 본체개발 |
| `cluster:dev:contracts:01412725:2025q3` | multi-contract count/sum/ranking/open | 두산퓨얼셀 / 2025 Q3 / 3 docs | count=3; total=107400000000; max=연료전지 시스템 공급 계약 |
| `cluster:dev:contracts:00126478:2025q1` | multi-contract count/sum/ranking/open | 삼성중공업 / 2025 Q1 / 3 docs | count=3; total=2781200000000; max=셔틀탱커 9척 |
| `cluster:dev:terminations:01515323:2025` | termination exists/sum/open | LG에너지솔루션 / 2025 / 2 docs | count=2; terminated total=13524786000000 |
| `cluster:dev:terminations:00126478:2025` | termination exists/sum/open | 삼성중공업 / 2025 / 2 docs | count=2; terminated total=4852500000000 |
| `cluster:dev:terminations:01316245:2025` | termination exists/sum/open | 효성중공업 / 2025 / 2 docs | count=2; terminated total=403666088000 |
| `cluster:dev:terminations:01412725:2025` | termination exists/sum/open | 두산퓨얼셀 / 2025 / 3 docs | count=3; terminated total=817900000000 |
| `cluster:dev:terminations:00126308:2025` | termination exists/sum/open | 삼성E&A / 2025 / 1 docs | count=1; terminated total=186755793747 |
| `cluster:dev:terminations:00126478:2026` | termination exists/sum/open | 삼성중공업 / 2026 / 1 docs | count=1; terminated total=114800000000 |
| `cluster:dev:facility:exchange_20250620800077` | facility amount/date | 한미반도체 / 한미반도체 7공장 | amount=28,480,000,000; end=2026-11-30 |
| `cluster:dev:facility:exchange_20251127800903` | facility amount/date | LG이노텍 / 광학솔루션사업부 시설투자 | amount=341,100,000,000; end=2026-12-31 |
| `cluster:dev:facility:exchange_20251217800832` | facility amount/date | 두산에너빌리티 / SMR 전용공장 신축 및 기존 공장 최적화, 혁신제조 시설 구축 | amount=806,800,000,000; end=2031-06-30 |
| `cluster:dev:facility:exchange_20251016800144` | facility amount/date | HMM / 컨테이너선 및 VLCC 신조 | amount=4,027,398,930,000; end=2029-04-30 |
| `cluster:dev:facility:exchange_20250730800037` | facility amount/date | 효성중공업 / HVDC(초고압 직류송전)용 변압기 공장 신설 | amount=253,800,000,000; end=2027-07-31 |
| `cluster:dev:rights:major_20250314000027` | rights offering shares/funds | 삼성SDI | common=11821000; other=0; facility funds=454100000000 |
| `cluster:dev:rights:major_20251215000398` | rights offering shares/funds | 고려아연 | common=2209716; other=0; facility funds=0 |
| `cluster:dev:rights:major_20250204000409` | rights offering shares/funds | 알테오젠 | common=0; other=434848; facility funds=54994177184 |
| `cluster:dev:rights:major_20250320001145` | rights offering shares/funds | 한화에어로스페이스 | common=5950500; other=0; facility funds=1200052500000 |
| `cluster:dev:business-change:samsung-sdi:2023-2025` | business-change synthesis | 삼성SDI 2023/2025 annual reports | 두 segment 모두 감소; two-year difference 구분 |
| `cluster:dev:business-change:hanwha-ocean:2023-2025` | business-change synthesis | 한화오션 2023/2025 annual reports | total revenue 증가; report YoY와 direct two-year change 구분 |

## Review response

전체가 적절하면 `batch-01 accept`라고 답하면 됩니다. 특정 cluster만 제외하려면 cluster ID와 이유만 적으면 됩니다.

## Actual case review

아래가 실제 runtime에 들어가는 question입니다. 각 case에서 Question과 Expected만 판단하면 됩니다.

- `accept`: 질문의 scope와 expected answer가 적절함
- `reject`: 질문 자체가 불필요하거나 scope/expected가 잘못됨

<details>
<summary><code>cluster:dev:contract:exchange_20250728800035</code> — 5 cases</summary>

### `case:dev:contract:20250728800035:amount`

- **Question:** 삼성전자의 '반도체 위탁생산 공급계약' 공시에서 계약금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 22764764160000 KRW (tolerance=0)
- **Documents:** exchange_20250728800035
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250728800035:end`

- **Question:** 삼성전자의 '반도체 위탁생산 공급계약' 공시에서 계약 종료일은 언제인가?
- **Test:** `search_and_extraction / date_lookup / closed / answerable`
- **Expected:** 2033-12-31
- **Documents:** exchange_20250728800035
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250728800035:ratio`

- **Question:** 삼성전자의 '반도체 위탁생산 공급계약' 공시에서 계약금액은 최근 매출액의 몇 퍼센트인가?
- **Test:** `multiple_retrieval_comparison_calculation / ratio / closed / answerable`
- **Expected:** 7.6 PERCENT (tolerance=0)
- **Documents:** exchange_20250728800035
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250728800035:recognized-revenue`

- **Question:** 삼성전자의 해당 계약에서 실제로 인식된 매출은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액만으로 실제 인식 매출을 알 수 없다."]; forbidden: ["Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250728800035
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250728800035:summary`

- **Question:** 삼성전자의 '반도체 위탁생산 공급계약' 공시 내용을 계약금액, 계약 종료일, 최근 매출액 대비 비율 기준으로 정리해줘.
- **Test:** `search_and_extraction / single_document_summary / open / answerable`
- **Expected:** required: [{"contract_amount":"22764764160000","unit":"KRW"},{"contract_end_date":"2033-12-31"},{"sales_ratio":"7.6","unit":"PERCENT"}]; forbidden: ["Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250728800035
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:contract:exchange_20250114800153</code> — 5 cases</summary>

### `case:dev:contract:20250114800153:amount`

- **Question:** 한미반도체의 'HBM 제조용 장비 수주' 공시에서 계약금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 10807500000 KRW (tolerance=0)
- **Documents:** exchange_20250114800153
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250114800153:end`

- **Question:** 한미반도체의 'HBM 제조용 장비 수주' 공시에서 계약 종료일은 언제인가?
- **Test:** `search_and_extraction / date_lookup / closed / answerable`
- **Expected:** 2025-07-01
- **Documents:** exchange_20250114800153
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250114800153:ratio`

- **Question:** 한미반도체의 'HBM 제조용 장비 수주' 공시에서 계약금액은 최근 매출액의 몇 퍼센트인가?
- **Test:** `multiple_retrieval_comparison_calculation / ratio / closed / answerable`
- **Expected:** 6.80 PERCENT (tolerance=0)
- **Documents:** exchange_20250114800153
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250114800153:recognized-revenue`

- **Question:** 한미반도체의 해당 계약에서 실제로 인식된 매출은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액만으로 실제 인식 매출을 알 수 없다."]; forbidden: ["Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250114800153
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250114800153:summary`

- **Question:** 한미반도체의 'HBM 제조용 장비 수주' 공시 내용을 계약금액, 계약 종료일, 최근 매출액 대비 비율 기준으로 정리해줘.
- **Test:** `search_and_extraction / single_document_summary / open / answerable`
- **Expected:** required: [{"contract_amount":"10807500000","unit":"KRW"},{"contract_end_date":"2025-07-01"},{"sales_ratio":"6.80","unit":"PERCENT"}]; forbidden: ["Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250114800153
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:contract:exchange_20250731800497</code> — 4 cases</summary>

### `case:dev:contract:20250731800497:amount`

- **Question:** 현대오토에버의 'hCloud 서비스 제공 계약' 공시에서 계약금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 125514000000 KRW (tolerance=0)
- **Documents:** exchange_20250731800497
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250731800497:end`

- **Question:** 현대오토에버의 'hCloud 서비스 제공 계약' 공시에서 계약 종료일은 언제인가?
- **Test:** `search_and_extraction / date_lookup / closed / answerable`
- **Expected:** 2030-06-30
- **Documents:** exchange_20250731800497
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250731800497:ratio`

- **Question:** 현대오토에버의 'hCloud 서비스 제공 계약' 공시에서 계약금액은 최근 매출액의 몇 퍼센트인가?
- **Test:** `multiple_retrieval_comparison_calculation / ratio / closed / answerable`
- **Expected:** 3.4 PERCENT (tolerance=0)
- **Documents:** exchange_20250731800497
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250731800497:recognized-revenue`

- **Question:** 현대오토에버의 해당 계약에서 실제로 인식된 매출은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액만으로 실제 인식 매출을 알 수 없다."]; forbidden: ["Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250731800497
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:contract:exchange_20250623800158</code> — 4 cases</summary>

### `case:dev:contract:20250623800158:amount`

- **Question:** LG씨엔에스의 '죽전 데이터센터 Co-location 서비스 계약서' 공시에서 계약금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액은 공개되지 않았다."]; forbidden: ["Any exact contract amount"]
- **Documents:** exchange_20250623800158
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250623800158:end`

- **Question:** LG씨엔에스의 '죽전 데이터센터 Co-location 서비스 계약서' 공시에서 계약 종료일은 언제인가?
- **Test:** `search_and_extraction / date_lookup / closed / answerable`
- **Expected:** 2033-05-31
- **Documents:** exchange_20250623800158
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250623800158:ratio`

- **Question:** LG씨엔에스의 '죽전 데이터센터 Co-location 서비스 계약서' 공시에서 계약금액은 최근 매출액의 몇 퍼센트인가?
- **Test:** `multiple_retrieval_comparison_calculation / ratio / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["매출액 대비 비율은 공개되지 않았다."]; forbidden: ["Any exact sales ratio"]
- **Documents:** exchange_20250623800158
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250623800158:recognized-revenue`

- **Question:** LG씨엔에스의 해당 계약에서 실제로 인식된 매출은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액만으로 실제 인식 매출을 알 수 없다."]; forbidden: ["Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250623800158
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:contract:exchange_20250114800022</code> — 4 cases</summary>

### `case:dev:contract:20250114800022:amount`

- **Question:** 삼성바이오로직스의 '의약품 위탁생산계약' 공시에서 계약금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 2074694843000 KRW (tolerance=0)
- **Documents:** exchange_20250114800022
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250114800022:end`

- **Question:** 삼성바이오로직스의 '의약품 위탁생산계약' 공시에서 계약 종료일은 언제인가?
- **Test:** `search_and_extraction / date_lookup / closed / answerable`
- **Expected:** 2030-12-31
- **Documents:** exchange_20250114800022
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250114800022:ratio`

- **Question:** 삼성바이오로직스의 '의약품 위탁생산계약' 공시에서 계약금액은 최근 매출액의 몇 퍼센트인가?
- **Test:** `multiple_retrieval_comparison_calculation / ratio / closed / answerable`
- **Expected:** 56.15 PERCENT (tolerance=0)
- **Documents:** exchange_20250114800022
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250114800022:recognized-revenue`

- **Question:** 삼성바이오로직스의 해당 계약에서 실제로 인식된 매출은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액만으로 실제 인식 매출을 알 수 없다."]; forbidden: ["Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250114800022
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:contract:exchange_20250326800989</code> — 4 cases</summary>

### `case:dev:contract:20250326800989:amount`

- **Question:** 한국항공우주의 '소형무장헬기 2차양산 기체 PBL 사업' 공시에서 계약금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 112893000000 KRW (tolerance=0)
- **Documents:** exchange_20250326800989
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250326800989:end`

- **Question:** 한국항공우주의 '소형무장헬기 2차양산 기체 PBL 사업' 공시에서 계약 종료일은 언제인가?
- **Test:** `search_and_extraction / date_lookup / closed / answerable`
- **Expected:** 2028-03-24
- **Documents:** exchange_20250326800989
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250326800989:ratio`

- **Question:** 한국항공우주의 '소형무장헬기 2차양산 기체 PBL 사업' 공시에서 계약금액은 최근 매출액의 몇 퍼센트인가?
- **Test:** `multiple_retrieval_comparison_calculation / ratio / closed / answerable`
- **Expected:** 3.0 PERCENT (tolerance=0)
- **Documents:** exchange_20250326800989
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250326800989:recognized-revenue`

- **Question:** 한국항공우주의 해당 계약에서 실제로 인식된 매출은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액만으로 실제 인식 매출을 알 수 없다."]; forbidden: ["Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250326800989
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:contract:exchange_20250210801035</code> — 4 cases</summary>

### `case:dev:contract:20250210801035:amount`

- **Question:** 한화오션의 'LNGC 2척' 공시에서 계약금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 732200000000 KRW (tolerance=0)
- **Documents:** exchange_20250210801035
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250210801035:end`

- **Question:** 한화오션의 'LNGC 2척' 공시에서 계약 종료일은 언제인가?
- **Test:** `search_and_extraction / date_lookup / closed / answerable`
- **Expected:** 2027-09-30
- **Documents:** exchange_20250210801035
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250210801035:ratio`

- **Question:** 한화오션의 'LNGC 2척' 공시에서 계약금액은 최근 매출액의 몇 퍼센트인가?
- **Test:** `multiple_retrieval_comparison_calculation / ratio / closed / answerable`
- **Expected:** 9.9 PERCENT (tolerance=0)
- **Documents:** exchange_20250210801035
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250210801035:recognized-revenue`

- **Question:** 한화오션의 해당 계약에서 실제로 인식된 매출은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액만으로 실제 인식 매출을 알 수 없다."]; forbidden: ["Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250210801035
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:contract:exchange_20250226800006</code> — 4 cases</summary>

### `case:dev:contract:20250226800006:amount`

- **Question:** 현대로템의 '모로코 철도청 전동차 사업' 공시에서 계약금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 2202726004050 KRW (tolerance=0)
- **Documents:** exchange_20250226800006
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250226800006:end`

- **Question:** 현대로템의 '모로코 철도청 전동차 사업' 공시에서 계약 종료일은 언제인가?
- **Test:** `search_and_extraction / date_lookup / closed / answerable`
- **Expected:** 2034-01-25
- **Documents:** exchange_20250226800006
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250226800006:ratio`

- **Question:** 현대로템의 '모로코 철도청 전동차 사업' 공시에서 계약금액은 최근 매출액의 몇 퍼센트인가?
- **Test:** `multiple_retrieval_comparison_calculation / ratio / closed / answerable`
- **Expected:** 61.4 PERCENT (tolerance=0)
- **Documents:** exchange_20250226800006
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250226800006:recognized-revenue`

- **Question:** 현대로템의 해당 계약에서 실제로 인식된 매출은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액만으로 실제 인식 매출을 알 수 없다."]; forbidden: ["Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250226800006
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:contract:exchange_20250123800036</code> — 4 cases</summary>

### `case:dev:contract:20250123800036:amount`

- **Question:** HD현대중공업의 '초대형 컨테이너선 12척' 공시에서 계약금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 3716000000000 KRW (tolerance=0)
- **Documents:** exchange_20250123800036
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250123800036:end`

- **Question:** HD현대중공업의 '초대형 컨테이너선 12척' 공시에서 계약 종료일은 언제인가?
- **Test:** `search_and_extraction / date_lookup / closed / answerable`
- **Expected:** 2028-12-29
- **Documents:** exchange_20250123800036
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250123800036:ratio`

- **Question:** HD현대중공업의 '초대형 컨테이너선 12척' 공시에서 계약금액은 최근 매출액의 몇 퍼센트인가?
- **Test:** `multiple_retrieval_comparison_calculation / ratio / closed / answerable`
- **Expected:** 31.06 PERCENT (tolerance=0)
- **Documents:** exchange_20250123800036
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250123800036:recognized-revenue`

- **Question:** HD현대중공업의 해당 계약에서 실제로 인식된 매출은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액만으로 실제 인식 매출을 알 수 없다."]; forbidden: ["Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250123800036
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:contract:exchange_20250313800043</code> — 4 cases</summary>

### `case:dev:contract:20250313800043:amount`

- **Question:** 두산에너빌리티의 'Rumah #1 IPP' 공시에서 계약금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 1128260775513 KRW (tolerance=0)
- **Documents:** exchange_20250313800043
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250313800043:end`

- **Question:** 두산에너빌리티의 'Rumah #1 IPP' 공시에서 계약 종료일은 언제인가?
- **Test:** `search_and_extraction / date_lookup / closed / answerable`
- **Expected:** 2028-05-31
- **Documents:** exchange_20250313800043
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250313800043:ratio`

- **Question:** 두산에너빌리티의 'Rumah #1 IPP' 공시에서 계약금액은 최근 매출액의 몇 퍼센트인가?
- **Test:** `multiple_retrieval_comparison_calculation / ratio / closed / answerable`
- **Expected:** 6.41 PERCENT (tolerance=0)
- **Documents:** exchange_20250313800043
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250313800043:recognized-revenue`

- **Question:** 두산에너빌리티의 해당 계약에서 실제로 인식된 매출은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액만으로 실제 인식 매출을 알 수 없다."]; forbidden: ["Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250313800043
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:contract:exchange_20250318800092</code> — 4 cases</summary>

### `case:dev:contract:20250318800092:amount`

- **Question:** 엘에스일렉트릭의 'Big Tech Data Center PJT' 공시에서 계약금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 162527055440 KRW (tolerance=0)
- **Documents:** exchange_20250318800092
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250318800092:end`

- **Question:** 엘에스일렉트릭의 'Big Tech Data Center PJT' 공시에서 계약 종료일은 언제인가?
- **Test:** `search_and_extraction / date_lookup / closed / answerable`
- **Expected:** 2025-10-27
- **Documents:** exchange_20250318800092
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250318800092:ratio`

- **Question:** 엘에스일렉트릭의 'Big Tech Data Center PJT' 공시에서 계약금액은 최근 매출액의 몇 퍼센트인가?
- **Test:** `multiple_retrieval_comparison_calculation / ratio / closed / answerable`
- **Expected:** 3.8 PERCENT (tolerance=0)
- **Documents:** exchange_20250318800092
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250318800092:recognized-revenue`

- **Question:** 엘에스일렉트릭의 해당 계약에서 실제로 인식된 매출은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액만으로 실제 인식 매출을 알 수 없다."]; forbidden: ["Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250318800092
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:contract:exchange_20250616800147</code> — 4 cases</summary>

### `case:dev:contract:20250616800147:amount`

- **Question:** LG에너지솔루션의 '전기차 배터리 공급계약' 공시에서 계약금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액은 공개되지 않았다."]; forbidden: ["Any exact contract amount"]
- **Documents:** exchange_20250616800147
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250616800147:end`

- **Question:** LG에너지솔루션의 '전기차 배터리 공급계약' 공시에서 계약 종료일은 언제인가?
- **Test:** `search_and_extraction / date_lookup / closed / answerable`
- **Expected:** 2030-12-31
- **Documents:** exchange_20250616800147
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250616800147:ratio`

- **Question:** LG에너지솔루션의 '전기차 배터리 공급계약' 공시에서 계약금액은 최근 매출액의 몇 퍼센트인가?
- **Test:** `multiple_retrieval_comparison_calculation / ratio / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["매출액 대비 비율은 공개되지 않았다."]; forbidden: ["Any exact sales ratio"]
- **Documents:** exchange_20250616800147
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contract:20250616800147:recognized-revenue`

- **Question:** LG에너지솔루션의 해당 계약에서 실제로 인식된 매출은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액만으로 실제 인식 매출을 알 수 없다."]; forbidden: ["Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250616800147
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:contracts:00164478:2025q1</code> — 6 cases</summary>

### `case:dev:contracts:00164478:2025q1:count`

- **Question:** 현대건설의 2025년 1분기 단일판매·공급계약 공시 중 계약금액이 공개된 계약은 몇 건인가?
- **Test:** `multiple_retrieval_comparison_calculation / count / closed / answerable`
- **Expected:** 2
- **Documents:** exchange_20250213800021, exchange_20250218800084
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00164478:2025q1:sum`

- **Question:** 현대건설의 2025년 1분기 단일판매·공급계약 공시에서 계약금액 합계는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / sum / closed / answerable`
- **Expected:** 2814485600000 KRW (tolerance=0)
- **Documents:** exchange_20250213800021, exchange_20250218800084
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00164478:2025q1:ranking`

- **Question:** 현대건설의 2025년 1분기 단일판매·공급계약 공시 중 계약금액이 가장 큰 계약은 무엇인가?
- **Test:** `multiple_retrieval_comparison_calculation / ranking / closed / answerable`
- **Expected:** checks: [{"field":"contract_name","operator":"string_equal","expected":"가양동 CJ부지 업무복합시설 신축공사"},{"field":"contract_amount","operator":"numeric_equal","expected":"1626673000000","unit":"KRW"}]
- **Documents:** exchange_20250213800021, exchange_20250218800084
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00164478:2025q1:summary`

- **Question:** 현대건설의 2025년 1분기 단일판매·공급계약 공시를 계약명, 금액, 계약상대, 기간 기준으로 정리해줘.
- **Test:** `multiple_retrieval_comparison_calculation / event_aggregation / open / answerable`
- **Expected:** required: [{"contract_name":"서울역 밀레니엄힐튼호텔 부지 개발사업 및 철거공사","amount":"1187812600000","counterparty":"와이디427피에프브이 주식회사","period":{"start":"-","end":"-"}},{"contract_name":"가양동 CJ부지 업무복합시설 신축공사","amount":"1626673000000","counterparty":"인창개발 주식회사","period":{"start":"-","end":"-"}}]; forbidden: ["Omit a scoped disclosed-amount contract.","Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250213800021, exchange_20250218800084
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00164478:2025q1:recognized-revenue`

- **Question:** 현대건설의 해당 계약들에서 실제로 인식된 매출 합계는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / sum / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액 합계만으로 실제 인식 매출을 알 수 없다."]; forbidden: ["Return contract total as recognized revenue."]
- **Documents:** exchange_20250213800021, exchange_20250218800084
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00164478:2025q1:difference`

- **Question:** 현대건설의 2025년 1분기 단일판매·공급계약 공시에서 계약금액 1위와 2위의 차이는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / difference / closed / answerable`
- **Expected:** 438860400000 KRW (tolerance=0)
- **Documents:** exchange_20250218800084, exchange_20250213800021
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:contracts:00124540:2025q1</code> — 6 cases</summary>

### `case:dev:contracts:00124540:2025q1:count`

- **Question:** 대우건설의 2025년 1분기 단일판매·공급계약 공시 중 계약금액이 공개된 계약은 몇 건인가?
- **Test:** `multiple_retrieval_comparison_calculation / count / closed / answerable`
- **Expected:** 3
- **Documents:** exchange_20250124800250, exchange_20250228800355, exchange_20250326801705
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00124540:2025q1:sum`

- **Question:** 대우건설의 2025년 1분기 단일판매·공급계약 공시에서 계약금액 합계는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / sum / closed / answerable`
- **Expected:** 1638691456115 KRW (tolerance=0)
- **Documents:** exchange_20250124800250, exchange_20250228800355, exchange_20250326801705
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00124540:2025q1:ranking`

- **Question:** 대우건설의 2025년 1분기 단일판매·공급계약 공시 중 계약금액이 가장 큰 계약은 무엇인가?
- **Test:** `multiple_retrieval_comparison_calculation / ranking / closed / answerable`
- **Expected:** checks: [{"field":"contract_name","operator":"string_equal","expected":"개포주공5단지아파트 재건축정비사업"},{"field":"contract_amount","operator":"numeric_equal","expected":"697033565000","unit":"KRW"}]
- **Documents:** exchange_20250124800250, exchange_20250228800355, exchange_20250326801705
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00124540:2025q1:summary`

- **Question:** 대우건설의 2025년 1분기 단일판매·공급계약 공시를 계약명, 금액, 계약상대, 기간 기준으로 정리해줘.
- **Test:** `multiple_retrieval_comparison_calculation / event_aggregation / open / answerable`
- **Expected:** required: [{"contract_name":"청주 분평미평지구 공동주택 신축사업","amount":"414251891115","counterparty":"(주)청주글로벌","period":{"start":"-","end":"-"}},{"contract_name":"개포주공5단지아파트 재건축정비사업","amount":"697033565000","counterparty":"개포주공5단지아파트 재건축정비사업조합","period":{"start":"-","end":"-"}},{"contract_name":"청라 국제업무단지 B1블록 오피스텔 신축사업","amount":"527406000000","counterparty":"(주)청라스마트시티","period":{"start":"-","end":"-"}}]; forbidden: ["Omit a scoped disclosed-amount contract.","Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250124800250, exchange_20250228800355, exchange_20250326801705
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00124540:2025q1:recognized-revenue`

- **Question:** 대우건설의 해당 계약들에서 실제로 인식된 매출 합계는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / sum / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액 합계만으로 실제 인식 매출을 알 수 없다."]; forbidden: ["Return contract total as recognized revenue."]
- **Documents:** exchange_20250124800250, exchange_20250228800355, exchange_20250326801705
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00124540:2025q1:difference`

- **Question:** 대우건설의 2025년 1분기 단일판매·공급계약 공시에서 계약금액 1위와 2위의 차이는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / difference / closed / answerable`
- **Expected:** 169627565000 KRW (tolerance=0)
- **Documents:** exchange_20250228800355, exchange_20250326801705
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:contracts:00126308:2025q1</code> — 5 cases</summary>

### `case:dev:contracts:00126308:2025q1:count`

- **Question:** 삼성E&A의 2025년 1분기 단일판매·공급계약 공시 중 계약금액이 공개된 계약은 몇 건인가?
- **Test:** `multiple_retrieval_comparison_calculation / count / closed / answerable`
- **Expected:** 3
- **Documents:** exchange_20250110800218, exchange_20250203800490, exchange_20250324800024
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00126308:2025q1:sum`

- **Question:** 삼성E&A의 2025년 1분기 단일판매·공급계약 공시에서 계약금액 합계는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / sum / closed / answerable`
- **Expected:** 3815056116698 KRW (tolerance=0)
- **Documents:** exchange_20250110800218, exchange_20250203800490, exchange_20250324800024
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00126308:2025q1:ranking`

- **Question:** 삼성E&A의 2025년 1분기 단일판매·공급계약 공시 중 계약금액이 가장 큰 계약은 무엇인가?
- **Test:** `multiple_retrieval_comparison_calculation / ranking / closed / answerable`
- **Expected:** checks: [{"field":"contract_name","operator":"string_equal","expected":"UAE Methanol Project"},{"field":"contract_amount","operator":"numeric_equal","expected":"2478818000000","unit":"KRW"}]
- **Documents:** exchange_20250110800218, exchange_20250203800490, exchange_20250324800024
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00126308:2025q1:summary`

- **Question:** 삼성E&A의 2025년 1분기 단일판매·공급계약 공시를 계약명, 금액, 계약상대, 기간 기준으로 정리해줘.
- **Test:** `multiple_retrieval_comparison_calculation / event_aggregation / open / answerable`
- **Expected:** required: [{"contract_name":"말레이시아 New Biorefinery Project","amount":"817610116698","counterparty":"PENGERANG BIOREFINERY SDN. BHD","period":{"start":"2025-01-08","end":"2028-09-07"}},{"contract_name":"UAE Methanol Project","amount":"2478818000000","counterparty":"ABU DHABI NATIONAL OIL COMPANY (ADNOC)","period":{"start":"2025-02-07","end":"2028-09-18"}},{"contract_name":"싸토리우스 송도 캠퍼스 프로젝트","amount":"518628000000","counterparty":"싸토리우스코리아오퍼레이션스 유한회사 (Sartorius Korea Operations LLC)","period":{"start":"2025-03-21","end":"2027-02-28"}}]; forbidden: ["Omit a scoped disclosed-amount contract.","Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250110800218, exchange_20250203800490, exchange_20250324800024
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00126308:2025q1:recognized-revenue`

- **Question:** 삼성E&A의 해당 계약들에서 실제로 인식된 매출 합계는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / sum / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액 합계만으로 실제 인식 매출을 알 수 없다."]; forbidden: ["Return contract total as recognized revenue."]
- **Documents:** exchange_20250110800218, exchange_20250203800490, exchange_20250324800024
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:contracts:00503668:2025q2</code> — 5 cases</summary>

### `case:dev:contracts:00503668:2025q2:count`

- **Question:** LIG디펜스앤에어로스페이스의 2025년 2분기 단일판매·공급계약 공시 중 계약금액이 공개된 계약은 몇 건인가?
- **Test:** `multiple_retrieval_comparison_calculation / count / closed / answerable`
- **Expected:** 5
- **Documents:** exchange_20250428800278, exchange_20250430801123, exchange_20250514800672, exchange_20250604800068, exchange_20250619800589
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00503668:2025q2:sum`

- **Question:** LIG디펜스앤에어로스페이스의 2025년 2분기 단일판매·공급계약 공시에서 계약금액 합계는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / sum / closed / answerable`
- **Expected:** 724229000000 KRW (tolerance=0)
- **Documents:** exchange_20250428800278, exchange_20250430801123, exchange_20250514800672, exchange_20250604800068, exchange_20250619800589
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00503668:2025q2:ranking`

- **Question:** LIG디펜스앤에어로스페이스의 2025년 2분기 단일판매·공급계약 공시 중 계약금액이 가장 큰 계약은 무엇인가?
- **Test:** `multiple_retrieval_comparison_calculation / ranking / closed / answerable`
- **Expected:** checks: [{"field":"contract_name","operator":"string_equal","expected":"정지궤도 기상.우주기상 위성 시스템 및 본체개발"},{"field":"contract_amount","operator":"numeric_equal","expected":"320754000000","unit":"KRW"}]
- **Documents:** exchange_20250428800278, exchange_20250430801123, exchange_20250514800672, exchange_20250604800068, exchange_20250619800589
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00503668:2025q2:summary`

- **Question:** LIG디펜스앤에어로스페이스의 2025년 2분기 단일판매·공급계약 공시를 계약명, 금액, 계약상대, 기간 기준으로 정리해줘.
- **Test:** `multiple_retrieval_comparison_calculation / event_aggregation / open / answerable`
- **Expected:** required: [{"contract_name":"장사정포요격체계 체계개발 체계종합 시제","amount":"83400000000","counterparty":"국방과학연구소","period":{"start":"2025-04-28","end":"2028-11-30"}},{"contract_name":"정지궤도 기상.우주기상 위성 시스템 및 본체개발","amount":"320754000000","counterparty":"한국기상산업기술원","period":{"start":"2025-04-01","end":"2031-12-31"}},{"contract_name":"체계종합 시제","amount":"98700000000","counterparty":"국방과학연구소","period":{"start":"2025-05-14","end":"2028-10-31"}},{"contract_name":"25년 신궁유도탄 외 2항목","amount":"138147000000","counterparty":"방위사업청","period":{"start":"2025-06-04","end":"2029-12-21"}},{"contract_name":"대포병탐지레이더-II PBL","amount":"83228000000","counterparty":"방위사업청","period":{"start":"2025-06-19","end":"2030-06-30"}}]; forbidden: ["Omit a scoped disclosed-amount contract.","Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250428800278, exchange_20250430801123, exchange_20250514800672, exchange_20250604800068, exchange_20250619800589
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00503668:2025q2:recognized-revenue`

- **Question:** LIG디펜스앤에어로스페이스의 해당 계약들에서 실제로 인식된 매출 합계는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / sum / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액 합계만으로 실제 인식 매출을 알 수 없다."]; forbidden: ["Return contract total as recognized revenue."]
- **Documents:** exchange_20250428800278, exchange_20250430801123, exchange_20250514800672, exchange_20250604800068, exchange_20250619800589
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:contracts:01412725:2025q3</code> — 5 cases</summary>

### `case:dev:contracts:01412725:2025q3:count`

- **Question:** 두산퓨얼셀의 2025년 3분기 단일판매·공급계약 공시 중 계약금액이 공개된 계약은 몇 건인가?
- **Test:** `multiple_retrieval_comparison_calculation / count / closed / answerable`
- **Expected:** 3
- **Documents:** exchange_20250822800038, exchange_20250822800050, exchange_20250822800053
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:01412725:2025q3:sum`

- **Question:** 두산퓨얼셀의 2025년 3분기 단일판매·공급계약 공시에서 계약금액 합계는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / sum / closed / answerable`
- **Expected:** 107400000000 KRW (tolerance=0)
- **Documents:** exchange_20250822800038, exchange_20250822800050, exchange_20250822800053
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:01412725:2025q3:ranking`

- **Question:** 두산퓨얼셀의 2025년 3분기 단일판매·공급계약 공시 중 계약금액이 가장 큰 계약은 무엇인가?
- **Test:** `multiple_retrieval_comparison_calculation / ranking / closed / answerable`
- **Expected:** checks: [{"field":"contract_name","operator":"string_equal","expected":"연료전지 시스템 공급 계약"},{"field":"contract_amount","operator":"numeric_equal","expected":"55400000000","unit":"KRW"}]
- **Documents:** exchange_20250822800038, exchange_20250822800050, exchange_20250822800053
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:01412725:2025q3:summary`

- **Question:** 두산퓨얼셀의 2025년 3분기 단일판매·공급계약 공시를 계약명, 금액, 계약상대, 기간 기준으로 정리해줘.
- **Test:** `multiple_retrieval_comparison_calculation / event_aggregation / open / answerable`
- **Expected:** required: [{"contract_name":"연료전지 시스템 공급 계약","amount":"55400000000","counterparty":"㈜삼천리이에스","period":{"start":"2025-08-21","end":"2026-10-15"}},{"contract_name":"연료전지 시스템 공급 계약","amount":"26000000000","counterparty":"㈜삼천리이에스","period":{"start":"2025-08-21","end":"2026-09-15"}},{"contract_name":"연료전지 시스템 공급 계약","amount":"26000000000","counterparty":"㈜삼천리이에스","period":{"start":"2025-08-21","end":"2026-11-15"}}]; forbidden: ["Omit a scoped disclosed-amount contract.","Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250822800038, exchange_20250822800050, exchange_20250822800053
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:01412725:2025q3:recognized-revenue`

- **Question:** 두산퓨얼셀의 해당 계약들에서 실제로 인식된 매출 합계는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / sum / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액 합계만으로 실제 인식 매출을 알 수 없다."]; forbidden: ["Return contract total as recognized revenue."]
- **Documents:** exchange_20250822800038, exchange_20250822800050, exchange_20250822800053
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:contracts:00126478:2025q1</code> — 5 cases</summary>

### `case:dev:contracts:00126478:2025q1:count`

- **Question:** 삼성중공업의 2025년 1분기 단일판매·공급계약 공시 중 계약금액이 공개된 계약은 몇 건인가?
- **Test:** `multiple_retrieval_comparison_calculation / count / closed / answerable`
- **Expected:** 3
- **Documents:** exchange_20250120800318, exchange_20250317800118, exchange_20250318800145
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00126478:2025q1:sum`

- **Question:** 삼성중공업의 2025년 1분기 단일판매·공급계약 공시에서 계약금액 합계는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / sum / closed / answerable`
- **Expected:** 2781200000000 KRW (tolerance=0)
- **Documents:** exchange_20250120800318, exchange_20250317800118, exchange_20250318800145
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00126478:2025q1:ranking`

- **Question:** 삼성중공업의 2025년 1분기 단일판매·공급계약 공시 중 계약금액이 가장 큰 계약은 무엇인가?
- **Test:** `multiple_retrieval_comparison_calculation / ranking / closed / answerable`
- **Expected:** checks: [{"field":"contract_name","operator":"string_equal","expected":"셔틀탱커 9척"},{"field":"contract_amount","operator":"numeric_equal","expected":"1935500000000","unit":"KRW"}]
- **Documents:** exchange_20250120800318, exchange_20250317800118, exchange_20250318800145
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00126478:2025q1:summary`

- **Question:** 삼성중공업의 2025년 1분기 단일판매·공급계약 공시를 계약명, 금액, 계약상대, 기간 기준으로 정리해줘.
- **Test:** `multiple_retrieval_comparison_calculation / event_aggregation / open / answerable`
- **Expected:** required: [{"contract_name":"LNG 운반선 1척","amount":"379600000000","counterparty":"오세아니아 지역 선주","period":{"start":"2025-01-17","end":"2027-06-30"}},{"contract_name":"셔틀탱커 9척","amount":"1935500000000","counterparty":"오세아니아 지역 선주","period":{"start":"2025-03-14","end":"2028-12-31"}},{"contract_name":"에탄운반선 2척","amount":"466100000000","counterparty":"아시아 지역 선주","period":{"start":"2025-03-17","end":"2028-02-29"}}]; forbidden: ["Omit a scoped disclosed-amount contract.","Treat contract amount as recognized revenue."]
- **Documents:** exchange_20250120800318, exchange_20250317800118, exchange_20250318800145
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:contracts:00126478:2025q1:recognized-revenue`

- **Question:** 삼성중공업의 해당 계약들에서 실제로 인식된 매출 합계는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / sum / closed / unanswerable`
- **Expected:** UNANSWERABLE; required: ["계약금액 합계만으로 실제 인식 매출을 알 수 없다."]; forbidden: ["Return contract total as recognized revenue."]
- **Documents:** exchange_20250120800318, exchange_20250317800118, exchange_20250318800145
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:terminations:01515323:2025</code> — 4 cases</summary>

### `case:dev:terminations:01515323:2025:exists`

- **Question:** LG에너지솔루션의 2025년 계약해지 공시가 하나라도 존재하는가? 있다면 몇 건인가?
- **Test:** `complex_document_reasoning / termination_check / closed / answerable`
- **Expected:** checks: [{"field":"exists","operator":"boolean_equal","expected":true},{"field":"count","operator":"integer_equal","expected":2}]
- **Documents:** exchange_20251217800800, exchange_20251226800706
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:terminations:01515323:2025:sum`

- **Question:** LG에너지솔루션의 2025년 계약해지 공시에서 해지금액 합계는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / sum / closed / answerable`
- **Expected:** 13524786000000 KRW (tolerance=0)
- **Documents:** exchange_20251217800800, exchange_20251226800706
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:terminations:01515323:2025:summary`

- **Question:** LG에너지솔루션의 2025년 계약해지 공시를 계약명, 해지금액, 해지일, 해지 사유 기준으로 정리해줘.
- **Test:** `complex_document_reasoning / history_synthesis / open / answerable`
- **Expected:** required: [{"contract_name":"전기차 배터리 공급계약","terminated_amount":"9603075000000","termination_date":"2025-12-17","termination_reason":"거래 상대방의 계약 해지 통보"},{"contract_name":"전기차 배터리 공급계약","terminated_amount":"3921711000000","termination_date":"2025-12-26","termination_reason":"계약상대의 배터리 사업 철수로 상호 합의에 의한 계약 해지"}]; forbidden: ["Treat terminated amount as realized loss without evidence."]
- **Documents:** exchange_20251217800800, exchange_20251226800706
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:terminations:01515323:2025:plain-exists`

- **Question:** LG에너지솔루션의 2025년 계약해지 공시가 하나라도 존재하는가?
- **Test:** `complex_document_reasoning / exists / closed / answerable`
- **Expected:** true
- **Documents:** exchange_20251217800800, exchange_20251226800706
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:terminations:00126478:2025</code> — 4 cases</summary>

### `case:dev:terminations:00126478:2025:exists`

- **Question:** 삼성중공업의 2025년 계약해지 공시가 하나라도 존재하는가? 있다면 몇 건인가?
- **Test:** `complex_document_reasoning / termination_check / closed / answerable`
- **Expected:** checks: [{"field":"exists","operator":"boolean_equal","expected":true},{"field":"count","operator":"integer_equal","expected":2}]
- **Documents:** exchange_20250618800387, exchange_20250618800388
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:terminations:00126478:2025:sum`

- **Question:** 삼성중공업의 2025년 계약해지 공시에서 해지금액 합계는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / sum / closed / answerable`
- **Expected:** 4852500000000 KRW (tolerance=0)
- **Documents:** exchange_20250618800387, exchange_20250618800388
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:terminations:00126478:2025:summary`

- **Question:** 삼성중공업의 2025년 계약해지 공시를 계약명, 해지금액, 해지일, 해지 사유 기준으로 정리해줘.
- **Test:** `complex_document_reasoning / history_synthesis / open / answerable`
- **Expected:** required: [{"contract_name":"블록, 기자재 및 설계","terminated_amount":"2045300000000","termination_date":"2025-06-18","termination_reason":"선주사의 위법한 계약해지"},{"contract_name":"블록 및 기자재","terminated_amount":"2807200000000","termination_date":"2025-06-18","termination_reason":"선주사의 위법한 계약해지"}]; forbidden: ["Treat terminated amount as realized loss without evidence."]
- **Documents:** exchange_20250618800387, exchange_20250618800388
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:terminations:00126478:2025:plain-exists`

- **Question:** 삼성중공업의 2025년 계약해지 공시가 하나라도 존재하는가?
- **Test:** `complex_document_reasoning / exists / closed / answerable`
- **Expected:** true
- **Documents:** exchange_20250618800387, exchange_20250618800388
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:terminations:01316245:2025</code> — 3 cases</summary>

### `case:dev:terminations:01316245:2025:exists`

- **Question:** 효성중공업의 2025년 계약해지 공시가 하나라도 존재하는가? 있다면 몇 건인가?
- **Test:** `complex_document_reasoning / termination_check / closed / answerable`
- **Expected:** checks: [{"field":"exists","operator":"boolean_equal","expected":true},{"field":"count","operator":"integer_equal","expected":2}]
- **Documents:** exchange_20250429800893, exchange_20250508800712
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:terminations:01316245:2025:sum`

- **Question:** 효성중공업의 2025년 계약해지 공시에서 해지금액 합계는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / sum / closed / answerable`
- **Expected:** 403666088000 KRW (tolerance=0)
- **Documents:** exchange_20250429800893, exchange_20250508800712
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:terminations:01316245:2025:summary`

- **Question:** 효성중공업의 2025년 계약해지 공시를 계약명, 해지금액, 해지일, 해지 사유 기준으로 정리해줘.
- **Test:** `complex_document_reasoning / history_synthesis / open / answerable`
- **Expected:** required: [{"contract_name":"부산 온천동 주상복합 공사도급계약","terminated_amount":"112461800000","termination_date":"2025-04-28","termination_reason":"계약 효력 소멸에 따른 해지"},{"contract_name":"설치 및 시운전","terminated_amount":"291204288000","termination_date":"2025-05-07","termination_reason":"계약상대방의 계약 해지 통보"}]; forbidden: ["Treat terminated amount as realized loss without evidence."]
- **Documents:** exchange_20250429800893, exchange_20250508800712
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:terminations:01412725:2025</code> — 3 cases</summary>

### `case:dev:terminations:01412725:2025:exists`

- **Question:** 두산퓨얼셀의 2025년 계약해지 공시가 하나라도 존재하는가? 있다면 몇 건인가?
- **Test:** `complex_document_reasoning / termination_check / closed / answerable`
- **Expected:** checks: [{"field":"exists","operator":"boolean_equal","expected":true},{"field":"count","operator":"integer_equal","expected":3}]
- **Documents:** exchange_20250331802527, exchange_20250402800768, exchange_20250402800874
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:terminations:01412725:2025:sum`

- **Question:** 두산퓨얼셀의 2025년 계약해지 공시에서 해지금액 합계는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / sum / closed / answerable`
- **Expected:** 817900000000 KRW (tolerance=0)
- **Documents:** exchange_20250331802527, exchange_20250402800768, exchange_20250402800874
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:terminations:01412725:2025:summary`

- **Question:** 두산퓨얼셀의 2025년 계약해지 공시를 계약명, 해지금액, 해지일, 해지 사유 기준으로 정리해줘.
- **Test:** `complex_document_reasoning / history_synthesis / open / answerable`
- **Expected:** required: [{"contract_name":"연료전지 시스템 공급 계약","terminated_amount":"398800000000","termination_date":"2025-03-28","termination_reason":"착수지시서(NTP) 장기 미발급에 따른 계약 해지 합의"},{"contract_name":"연료전지 시스템 공급 계약","terminated_amount":"72200000000","termination_date":"2025-04-02","termination_reason":"PF금융약정 체결 무산에 따른 해지"},{"contract_name":"연료전지 공급 계약","terminated_amount":"346900000000","termination_date":"2025-04-02","termination_reason":"상호 합의에 의한 계약 해지"}]; forbidden: ["Treat terminated amount as realized loss without evidence."]
- **Documents:** exchange_20250331802527, exchange_20250402800768, exchange_20250402800874
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:terminations:00126308:2025</code> — 3 cases</summary>

### `case:dev:terminations:00126308:2025:exists`

- **Question:** 삼성E&A의 2025년 계약해지 공시가 하나라도 존재하는가? 있다면 몇 건인가?
- **Test:** `complex_document_reasoning / termination_check / closed / answerable`
- **Expected:** checks: [{"field":"exists","operator":"boolean_equal","expected":true},{"field":"count","operator":"integer_equal","expected":1}]
- **Documents:** exchange_20250407800036
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:terminations:00126308:2025:sum`

- **Question:** 삼성E&A의 2025년 계약해지 공시에서 해지금액 합계는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / sum / closed / answerable`
- **Expected:** 186755793747 KRW (tolerance=0)
- **Documents:** exchange_20250407800036
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:terminations:00126308:2025:summary`

- **Question:** 삼성E&A의 2025년 계약해지 공시를 계약명, 해지금액, 해지일, 해지 사유 기준으로 정리해줘.
- **Test:** `complex_document_reasoning / history_synthesis / open / answerable`
- **Expected:** required: [{"contract_name":"Contract Agreement in respect of Salamanca ULSD Project","terminated_amount":"186755793747","termination_date":"2025-04-04","termination_reason":"발주처의 계약 해지 통보"}]; forbidden: ["Treat terminated amount as realized loss without evidence."]
- **Documents:** exchange_20250407800036
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:terminations:00126478:2026</code> — 3 cases</summary>

### `case:dev:terminations:00126478:2026:exists`

- **Question:** 삼성중공업의 2026년 계약해지 공시가 하나라도 존재하는가? 있다면 몇 건인가?
- **Test:** `complex_document_reasoning / termination_check / closed / answerable`
- **Expected:** checks: [{"field":"exists","operator":"boolean_equal","expected":true},{"field":"count","operator":"integer_equal","expected":1}]
- **Documents:** exchange_20260316801038
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:terminations:00126478:2026:sum`

- **Question:** 삼성중공업의 2026년 계약해지 공시에서 해지금액 합계는 얼마인가?
- **Test:** `multiple_retrieval_comparison_calculation / sum / closed / answerable`
- **Expected:** 114800000000 KRW (tolerance=0)
- **Documents:** exchange_20260316801038
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:terminations:00126478:2026:summary`

- **Question:** 삼성중공업의 2026년 계약해지 공시를 계약명, 해지금액, 해지일, 해지 사유 기준으로 정리해줘.
- **Test:** `complex_document_reasoning / history_synthesis / open / answerable`
- **Expected:** required: [{"contract_name":"원유운반선 1척","terminated_amount":"114800000000","termination_date":"2026-03-14","termination_reason":"선주사의 계약 의무 불이행"}]; forbidden: ["Treat terminated amount as realized loss without evidence."]
- **Documents:** exchange_20260316801038
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:facility:exchange_20250620800077</code> — 2 cases</summary>

### `case:dev:facility:20250620800077:amount`

- **Question:** 한미반도체의 한미반도체 7공장 투자금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 28480000000 KRW (tolerance=0)
- **Documents:** exchange_20250620800077
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:facility:20250620800077:end`

- **Question:** 한미반도체의 한미반도체 7공장 투자 종료 예정일은 언제인가?
- **Test:** `search_and_extraction / date_lookup / closed / answerable`
- **Expected:** 2026-11-30
- **Documents:** exchange_20250620800077
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:facility:exchange_20251127800903</code> — 2 cases</summary>

### `case:dev:facility:20251127800903:amount`

- **Question:** LG이노텍의 광학솔루션사업부 시설투자 투자금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 341100000000 KRW (tolerance=0)
- **Documents:** exchange_20251127800903
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:facility:20251127800903:end`

- **Question:** LG이노텍의 광학솔루션사업부 시설투자 투자 종료 예정일은 언제인가?
- **Test:** `search_and_extraction / date_lookup / closed / answerable`
- **Expected:** 2026-12-31
- **Documents:** exchange_20251127800903
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:facility:exchange_20251217800832</code> — 2 cases</summary>

### `case:dev:facility:20251217800832:amount`

- **Question:** 두산에너빌리티의 SMR 전용공장 신축 및 기존 공장 최적화, 혁신제조 시설 구축 투자금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 806800000000 KRW (tolerance=0)
- **Documents:** exchange_20251217800832
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:facility:20251217800832:end`

- **Question:** 두산에너빌리티의 SMR 전용공장 신축 및 기존 공장 최적화, 혁신제조 시설 구축 투자 종료 예정일은 언제인가?
- **Test:** `search_and_extraction / date_lookup / closed / answerable`
- **Expected:** 2031-06-30
- **Documents:** exchange_20251217800832
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:facility:exchange_20251016800144</code> — 2 cases</summary>

### `case:dev:facility:20251016800144:amount`

- **Question:** HMM의 컨테이너선 및 VLCC 신조 투자금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 4027398930000 KRW (tolerance=0)
- **Documents:** exchange_20251016800144
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:facility:20251016800144:end`

- **Question:** HMM의 컨테이너선 및 VLCC 신조 투자 종료 예정일은 언제인가?
- **Test:** `search_and_extraction / date_lookup / closed / answerable`
- **Expected:** 2029-04-30
- **Documents:** exchange_20251016800144
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:facility:exchange_20250730800037</code> — 2 cases</summary>

### `case:dev:facility:20250730800037:amount`

- **Question:** 효성중공업의 HVDC(초고압 직류송전)용 변압기 공장 신설 투자금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 253800000000 KRW (tolerance=0)
- **Documents:** exchange_20250730800037
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:facility:20250730800037:end`

- **Question:** 효성중공업의 HVDC(초고압 직류송전)용 변압기 공장 신설 투자 종료 예정일은 언제인가?
- **Test:** `search_and_extraction / date_lookup / closed / answerable`
- **Expected:** 2027-07-31
- **Documents:** exchange_20250730800037
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:rights:major_20250314000027</code> — 2 cases</summary>

### `case:dev:rights:20250314000027:shares`

- **Question:** 삼성SDI의 2025년 유상증자 결정에서 새로 발행할 보통주와 기타주식 수는 각각 몇 주인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** checks: [{"field":"common_shares","operator":"integer_equal","expected":11821000},{"field":"other_shares","operator":"integer_equal","expected":0}]
- **Documents:** major_20250314000027
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:rights:20250314000027:facility-funds`

- **Question:** 삼성SDI의 해당 유상증자에서 시설자금으로 배정한 금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 454100000000 KRW (tolerance=0)
- **Documents:** major_20250314000027
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:rights:major_20251215000398</code> — 2 cases</summary>

### `case:dev:rights:20251215000398:shares`

- **Question:** 고려아연의 2025년 유상증자 결정에서 새로 발행할 보통주와 기타주식 수는 각각 몇 주인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** checks: [{"field":"common_shares","operator":"integer_equal","expected":2209716},{"field":"other_shares","operator":"integer_equal","expected":0}]
- **Documents:** major_20251215000398
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:rights:20251215000398:facility-funds`

- **Question:** 고려아연의 해당 유상증자에서 시설자금으로 배정한 금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 0 KRW (tolerance=0)
- **Documents:** major_20251215000398
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:rights:major_20250204000409</code> — 2 cases</summary>

### `case:dev:rights:20250204000409:shares`

- **Question:** 알테오젠의 2025년 유상증자 결정에서 새로 발행할 보통주와 기타주식 수는 각각 몇 주인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** checks: [{"field":"common_shares","operator":"integer_equal","expected":0},{"field":"other_shares","operator":"integer_equal","expected":434848}]
- **Documents:** major_20250204000409
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:rights:20250204000409:facility-funds`

- **Question:** 알테오젠의 해당 유상증자에서 시설자금으로 배정한 금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 54994177184 KRW (tolerance=0)
- **Documents:** major_20250204000409
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:rights:major_20250320001145</code> — 2 cases</summary>

### `case:dev:rights:20250320001145:shares`

- **Question:** 한화에어로스페이스의 2025년 유상증자 결정에서 새로 발행할 보통주와 기타주식 수는 각각 몇 주인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** checks: [{"field":"common_shares","operator":"integer_equal","expected":5950500},{"field":"other_shares","operator":"integer_equal","expected":0}]
- **Documents:** major_20250320001145
- **Review:** `[ ] accept`  `[ ] reject`

### `case:dev:rights:20250320001145:facility-funds`

- **Question:** 한화에어로스페이스의 해당 유상증자에서 시설자금으로 배정한 금액은 얼마인가?
- **Test:** `search_and_extraction / fact_lookup / closed / answerable`
- **Expected:** 1200052500000 KRW (tolerance=0)
- **Documents:** major_20250320001145
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:business-change:samsung-sdi:2023-2025</code> — 1 cases</summary>

### `case:dev:business-change:00126362:2023-2025`

- **Question:** 삼성SDI의 2023년과 2025년 사업보고서를 비교해 에너지솔루션과 전자재료 사업의 매출 구조가 어떻게 바뀌었는지 설명해줘.
- **Test:** `complex_document_reasoning / business_change_synthesis / open / answerable`
- **Expected:** required: [{"segment":"energy_solution","sales_2023":"20406100000000","sales_2025":"12384100000000","change":"-8022000000000","unit":"KRW"},{"segment":"electronic_materials","sales_2023":"2302200000000","sales_2025":"882600000000","change":"-1419600000000","unit":"KRW"},{"claim":"Both segments decreased; energy solution remained the larger segment."}]; forbidden: ["Claim that either segment grew from 2023 to 2025.","Treat each report’s YoY explanation as a direct causal explanation for the full two-year change."]
- **Documents:** periodic_20240312000853, periodic_20260310002954
- **Review:** `[ ] accept`  `[ ] reject`

</details>

<details>
<summary><code>cluster:dev:business-change:hanwha-ocean:2023-2025</code> — 1 cases</summary>

### `case:dev:business-change:00111704:2023-2025`

- **Question:** 한화오션의 2023년과 2025년 사업보고서를 비교해 연결 매출 규모와 상선·해양 및 특수선 사업의 흐름이 어떻게 달라졌는지 설명해줘.
- **Test:** `complex_document_reasoning / business_change_synthesis / open / answerable`
- **Expected:** required: [{"consolidated_revenue_2023":"7408300000000","consolidated_revenue_2025":"12783500000000","change":"5375200000000","unit":"KRW"},{"reported_yoy_2023":{"commercial_ship":"38.0","marine_and_special":"163.7"},"unit":"PERCENT"},{"reported_yoy_2025":{"commercial_ship":"21.3","marine_and_special":"-5.3"},"unit":"PERCENT"},{"claim":"Total revenue was higher in 2025, while marine and special ship sales changed from reported YoY growth in 2023 to reported YoY decline in 2025."}]; forbidden: ["State that 163.7% to -5.3% is the direct 2023-to-2025 revenue change.","State that total revenue fell from 2023 to 2025."]
- **Documents:** periodic_20240328000773, periodic_20260317000644
- **Review:** `[ ] accept`  `[ ] reject`

</details>

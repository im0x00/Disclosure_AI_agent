# development-mini-v1 review

이 문서는 JSONL을 열지 않고도 실제 question과 expected answer를 모두 볼 수 있는 review view입니다.

Reviewer가 볼 것은 **question이 intended logical task를 잘 표현하는지**입니다. Oracle fact와 raw evidence range는 별도 verification 대상으로 이미 다시 확인합니다.

## Suite summary

- Cases: 43
- Independent oracle clusters: 9
- Answerability: {"answerable": 36, "unanswerable": 7}
- Response mode: {"closed": 33, "open": 10}

## 1. cluster:dev:contract:exchange_20250728800035

### 1.1. 삼성전자의 '반도체 위탁생산 공급계약' 공시에서 계약금액은 얼마인가?

- Case: case:dev:contract:20250728800035:amount
- Expected: 22764764160000 KRW
- Axes: search_and_extraction / closed / fact_lookup / answerable
- Scope: event · Version: filed
- Documents: exchange_20250728800035

### 1.2. 삼성전자의 '반도체 위탁생산 공급계약' 공시에서 계약 종료일은 언제인가?

- Case: case:dev:contract:20250728800035:end
- Expected: 2033-12-31
- Axes: search_and_extraction / closed / date_lookup / answerable
- Scope: event · Version: filed
- Documents: exchange_20250728800035

### 1.3. 삼성전자의 '반도체 위탁생산 공급계약' 공시에서 계약금액은 최근 매출액의 몇 퍼센트인가?

- Case: case:dev:contract:20250728800035:ratio
- Expected: 7.6 PERCENT
- Axes: multiple_retrieval_comparison_calculation / closed / ratio / answerable
- Scope: event · Version: filed
- Documents: exchange_20250728800035

### 1.4. 삼성전자의 해당 계약에서 실제로 인식된 매출은 얼마인가?

- Case: case:dev:contract:20250728800035:recognized-revenue
- Expected: ABSTAIN — 계약금액만으로 실제 인식 매출을 알 수 없다.
- Axes: search_and_extraction / closed / fact_lookup / unanswerable
- Scope: event · Version: filed
- Documents: exchange_20250728800035

### 1.5. 삼성전자의 '반도체 위탁생산 공급계약' 공시 내용을 계약금액, 계약 종료일, 최근 매출액 대비 비율 기준으로 정리해줘.

- Case: case:dev:contract:20250728800035:summary
- Expected: REQUIRED — {"contract_amount": "22764764160000", "unit": "KRW"}; {"contract_end_date": "2033-12-31"}; {"sales_ratio": "7.6", "unit": "PERCENT"}
- Axes: search_and_extraction / open / single_document_summary / answerable
- Scope: event · Version: filed
- Documents: exchange_20250728800035

## 2. cluster:dev:contracts:01412725:2025q3

### 2.1. 두산퓨얼셀의 2025년 3분기 단일판매·공급계약 공시 중 계약금액이 공개된 계약은 몇 건인가?

- Case: case:dev:contracts:01412725:2025q3:count
- Expected: 3
- Axes: multiple_retrieval_comparison_calculation / closed / count / answerable
- Scope: company_and_filed_quarter · Version: filed
- Documents: exchange_20250822800038, exchange_20250822800050, exchange_20250822800053

### 2.2. 두산퓨얼셀의 2025년 3분기 단일판매·공급계약 공시에서 계약금액 합계는 얼마인가?

- Case: case:dev:contracts:01412725:2025q3:sum
- Expected: 107400000000 KRW
- Axes: multiple_retrieval_comparison_calculation / closed / sum / answerable
- Scope: company_and_filed_quarter · Version: filed
- Documents: exchange_20250822800038, exchange_20250822800050, exchange_20250822800053

### 2.3. 두산퓨얼셀의 2025년 3분기 단일판매·공급계약 공시 중 계약금액이 가장 큰 계약은 무엇인가?

- Case: case:dev:contracts:01412725:2025q3:ranking
- Expected: {"mode": "structured", "checks": [{"field": "contract_name", "operator": "string_equal", "expected": "연료전지 시스템 공급 계약"}, {"field": "contract_amount", "operator": "numeric_equal", "expected": "55400000000", "unit": "KRW"}]}
- Axes: multiple_retrieval_comparison_calculation / closed / ranking / answerable
- Scope: company_and_filed_quarter · Version: filed
- Documents: exchange_20250822800038, exchange_20250822800050, exchange_20250822800053

### 2.4. 두산퓨얼셀의 2025년 3분기 단일판매·공급계약 공시를 계약명, 금액, 계약상대, 기간 기준으로 정리해줘.

- Case: case:dev:contracts:01412725:2025q3:summary
- Expected: REQUIRED — {"contract_name": "연료전지 시스템 공급 계약", "amount": "55400000000", "counterparty": "㈜삼천리이에스", "period": {"start": "2025-08-21", "end": "2026-10-15"}}; {"contract_name": "연료전지 시스템 공급 계약", "amount": "26000000000", "counterparty": "㈜삼천리이에스", "period": {"start": "2025-08-21", "end": "2026-09-15"}}; {"contract_name": "연료전지 시스템 공급 계약", "amount": "26000000000", "counterparty": "㈜삼천리이에스", "period": {"start": "2025-08-21", "end": "2026-11-15"}}
- Axes: multiple_retrieval_comparison_calculation / open / event_aggregation / answerable
- Scope: company_and_filed_quarter · Version: filed
- Documents: exchange_20250822800038, exchange_20250822800050, exchange_20250822800053

### 2.5. 두산퓨얼셀의 해당 계약들에서 실제로 인식된 매출 합계는 얼마인가?

- Case: case:dev:contracts:01412725:2025q3:recognized-revenue
- Expected: ABSTAIN — 계약금액 합계만으로 실제 인식 매출을 알 수 없다.
- Axes: multiple_retrieval_comparison_calculation / closed / sum / unanswerable
- Scope: company_and_filed_quarter · Version: filed
- Documents: exchange_20250822800038, exchange_20250822800050, exchange_20250822800053

## 3. cluster:dev:terminations:01412725:2025

### 3.1. 두산퓨얼셀의 2025년 계약해지 공시가 하나라도 존재하는가? 있다면 몇 건인가?

- Case: case:dev:terminations:01412725:2025:exists
- Expected: {"mode": "structured", "checks": [{"field": "exists", "operator": "boolean_equal", "expected": true}, {"field": "count", "operator": "integer_equal", "expected": 3}]}
- Axes: complex_document_reasoning / closed / termination_check / answerable
- Scope: company_and_termination_year · Version: filed
- Documents: exchange_20250331802527, exchange_20250402800768, exchange_20250402800874

### 3.2. 두산퓨얼셀의 2025년 계약해지 공시에서 해지금액 합계는 얼마인가?

- Case: case:dev:terminations:01412725:2025:sum
- Expected: 817900000000 KRW
- Axes: multiple_retrieval_comparison_calculation / closed / sum / answerable
- Scope: company_and_termination_year · Version: filed
- Documents: exchange_20250331802527, exchange_20250402800768, exchange_20250402800874

### 3.3. 두산퓨얼셀의 2025년 계약해지 공시를 계약명, 해지금액, 해지일, 해지 사유 기준으로 정리해줘.

- Case: case:dev:terminations:01412725:2025:summary
- Expected: REQUIRED — {"contract_name": "연료전지 시스템 공급 계약", "terminated_amount": "398800000000", "termination_date": "2025-03-28", "termination_reason": "착수지시서(NTP) 장기 미발급에 따른 계약 해지 합의"}; {"contract_name": "연료전지 시스템 공급 계약", "terminated_amount": "72200000000", "termination_date": "2025-04-02", "termination_reason": "PF금융약정 체결 무산에 따른 해지"}; {"contract_name": "연료전지 공급 계약", "terminated_amount": "346900000000", "termination_date": "2025-04-02", "termination_reason": "상호 합의에 의한 계약 해지"}
- Axes: complex_document_reasoning / open / history_synthesis / answerable
- Scope: company_and_termination_year · Version: filed
- Documents: exchange_20250331802527, exchange_20250402800768, exchange_20250402800874

## 4. cluster:dev:facility:exchange_20251016800144

### 4.1. HMM의 컨테이너선 및 VLCC 신조 투자금액은 얼마인가?

- Case: case:dev:facility:20251016800144:amount
- Expected: 4027398930000 KRW
- Axes: search_and_extraction / closed / fact_lookup / answerable
- Scope: event · Version: filed
- Documents: exchange_20251016800144

### 4.2. HMM의 컨테이너선 및 VLCC 신조 투자 종료 예정일은 언제인가?

- Case: case:dev:facility:20251016800144:end
- Expected: 2029-04-30
- Axes: search_and_extraction / closed / date_lookup / answerable
- Scope: event · Version: filed
- Documents: exchange_20251016800144

## 5. cluster:mw:samsung-contract-correction

### 5.1. 삼성전자의 2025년 7월 28일 반도체 위탁생산 계약 최초 공시에서 계약상대는 어떻게 표시됐는가?

- Case: case:mw:samsung-contract:initial-counterparty
- Expected: 글로벌 대형기업
- Axes: search_and_extraction / closed / fact_lookup / answerable
- Scope: event · Version: original_as_filed
- Documents: exchange_20250728800035

### 5.2. 삼성전자의 반도체 위탁생산 계약에서 2025년 12월 31일 기준 최종 공개된 계약상대는 누구인가?

- Case: case:mw:samsung-contract:latest-counterparty
- Expected: 테슬라 / Tesla / Tesla, Inc. / 테슬라(Tesla, Inc.)
- Axes: complex_document_reasoning / closed / correction_aware_lookup / answerable
- Scope: event_revision_chain · Version: latest_as_of_world_end
- Documents: exchange_20250728800035, exchange_20250731800028

### 5.3. 삼성전자의 2025년 7월 31일 정정 공시에서 계약금액도 변경됐는가?

- Case: case:mw:samsung-contract:amount-changed
- Expected: false
- Axes: complex_document_reasoning / closed / exists / answerable
- Scope: event_revision_chain · Version: compare_original_to_latest
- Documents: exchange_20250728800035, exchange_20250731800028

### 5.4. 삼성전자의 반도체 위탁생산 계약 최초 공시와 정정 공시를 비교해 무엇이 바뀌었는지 정리해줘.

- Case: case:mw:samsung-contract:correction-summary
- Expected: REQUIRED — 계약상대 표시는 '글로벌 대형기업'에서 '테슬라(Tesla, Inc.)'로 변경됐다.; 정정 사유는 계약상대 공개 동의다.; 계약금액 22,764,764,160,000원은 바뀌지 않았다.
- Axes: complex_document_reasoning / open / history_synthesis / answerable
- Scope: event_revision_chain · Version: compare_original_to_latest
- Documents: exchange_20250728800035, exchange_20250731800028

### 5.5. 삼성전자의 해당 계약은 2025년 12월 31일까지 몇 퍼센트 이행됐는가?

- Case: case:mw:samsung-contract:execution-rate
- Expected: ABSTAIN — 공시에는 계약 이행률이 없어 계산할 수 없다.
- Axes: search_and_extraction / closed / fact_lookup / unanswerable
- Scope: event · Version: latest_as_of_world_end
- Documents: exchange_20250731800028

## 6. cluster:mw:facility-hmm-doosan

### 6.1. 두산퓨얼셀 SOFC 생산설비 투자의 2025년 12월 31일 기준 최종 투자금액은 얼마인가?

- Case: case:mw:doosan-sofc:latest-amount
- Expected: 155800000000 KRW
- Axes: search_and_extraction / closed / fact_lookup / answerable
- Scope: event · Version: latest_as_of_world_end
- Documents: exchange_20250430800633

### 6.2. 두산퓨얼셀 SOFC 생산설비 투자의 최종 종료 예정일은 언제인가?

- Case: case:mw:doosan-sofc:latest-end
- Expected: 2025-06-30
- Axes: complex_document_reasoning / closed / correction_aware_lookup / answerable
- Scope: event_revision_chain · Version: latest_as_of_world_end
- Documents: exchange_20231228800377, exchange_20250430800633

### 6.3. HMM의 선박 신조 투자와 두산퓨얼셀의 SOFC 생산설비 투자 중 공시된 투자금액이 더 큰 것은 어느 회사인가?

- Case: case:mw:facility:hmm-vs-doosan:winner
- Expected: HMM
- Axes: multiple_retrieval_comparison_calculation / closed / comparison / answerable
- Scope: cross_company_events · Version: latest_as_of_world_end
- Documents: exchange_20250430800633, exchange_20251016800144

### 6.4. HMM의 선박 신조 투자금액은 두산퓨얼셀 SOFC 생산설비 투자금액보다 얼마 더 큰가?

- Case: case:mw:facility:hmm-vs-doosan:difference
- Expected: 3871598930000 KRW
- Axes: multiple_retrieval_comparison_calculation / closed / difference / answerable
- Scope: cross_company_events · Version: latest_as_of_world_end
- Documents: exchange_20250430800633, exchange_20251016800144

### 6.5. 2025년 12월 31일까지 HMM 선박 신조와 두산퓨얼셀 SOFC 설비에 실제 지급된 금액의 합계는 얼마인가?

- Case: case:mw:facility:hmm-doosan:paid
- Expected: ABSTAIN — 공시는 투자 계획 금액만 보여주며 실제 지급 누계는 제공하지 않는다.
- Axes: multiple_retrieval_comparison_calculation / closed / sum / unanswerable
- Scope: cross_company_events · Version: latest_as_of_world_end
- Documents: exchange_20250430800633, exchange_20251016800144

## 7. cluster:mw:woori-2025-funded-bonds

### 7.1. 우리금융지주 19회 상각형 조건부자본증권의 최초 공시 권면총액은 얼마인가?

- Case: case:mw:woori-bond19:initial-amount
- Expected: 270000000000 KRW
- Axes: search_and_extraction / closed / fact_lookup / answerable
- Scope: event · Version: original_as_filed
- Documents: major_20241220000592

### 7.2. 우리금융지주 19회 상각형 조건부자본증권의 최종 권면총액은 얼마인가?

- Case: case:mw:woori-bond19:latest-amount
- Expected: 400000000000 KRW
- Axes: complex_document_reasoning / closed / correction_aware_lookup / answerable
- Scope: event_revision_chain · Version: latest_as_of_world_end
- Documents: major_20241220000592, major_20250428000583, major_20250507000448

### 7.3. 우리금융지주 19회 상각형 조건부자본증권의 권면총액은 최초 공시보다 최종 공시에서 얼마 늘었는가?

- Case: case:mw:woori-bond19:difference
- Expected: 130000000000 KRW
- Axes: multiple_retrieval_comparison_calculation / closed / difference / answerable
- Scope: event_revision_chain · Version: compare_original_to_latest
- Documents: major_20241220000592, major_20250507000448

### 7.4. 우리금융지주 19회 상각형 조건부자본증권의 권면총액은 최초 공시 대비 최종 공시에서 몇 퍼센트 증가했는가?

- Case: case:mw:woori-bond19:percentage-change
- Expected: 48.14814814814814814814814815 PERCENT
- Axes: multiple_retrieval_comparison_calculation / closed / percentage_change / answerable
- Scope: event_revision_chain · Version: compare_original_to_latest
- Documents: major_20241220000592, major_20250507000448

### 7.5. 우리금융지주가 2025년에 납입한 상각형 조건부자본증권 발행은 몇 건인가?

- Case: case:mw:woori-2025-funded-bonds:count
- Expected: 2
- Axes: multiple_retrieval_comparison_calculation / closed / count / answerable
- Scope: company_and_payment_year · Version: latest_as_of_world_end
- Documents: major_20250507000448, major_20251016000086

### 7.6. 우리금융지주가 2025년에 납입한 상각형 조건부자본증권의 최종 권면총액 합계는 얼마인가?

- Case: case:mw:woori-2025-funded-bonds:total
- Expected: 800000000000 KRW
- Axes: multiple_retrieval_comparison_calculation / closed / sum / answerable
- Scope: company_and_payment_year · Version: latest_as_of_world_end
- Documents: major_20250507000448, major_20251016000086

### 7.7. 우리금융지주가 2025년에 납입한 상각형 조건부자본증권 발행을 회차, 최종 권면총액, 납입일, 자금 용도별로 정리해줘.

- Case: case:mw:woori-2025-funded-bonds:summary
- Expected: REQUIRED — {"round": 19, "amount": "400000000000", "payment_date": "2025-05-13", "debt_repayment": "300000000000", "operating_funds": "100000000000"}; {"round": 20, "amount": "400000000000", "payment_date": "2025-10-22", "debt_repayment": "200000000000", "operating_funds": "200000000000"}; {"total": "800000000000", "debt_repayment_total": "500000000000", "operating_funds_total": "300000000000"}
- Axes: multiple_retrieval_comparison_calculation / open / fundraising_aggregation / answerable
- Scope: company_and_payment_year · Version: latest_as_of_world_end
- Documents: major_20250507000448, major_20251016000086

### 7.8. 우리금융지주가 2025년 두 발행으로 조달한 돈을 실제로 어디에 얼마씩 썼는지 정리해줘.

- Case: case:mw:woori-2025-funded-bonds:actual-use
- Expected: ABSTAIN — 공시는 자금 사용 목적 또는 계획만 제시하며 실제 사용액은 확인할 수 없다.
- Axes: multiple_retrieval_comparison_calculation / open / fundraising_aggregation / unanswerable
- Scope: company_and_payment_year · Version: latest_as_of_world_end
- Documents: major_20250507000448, major_20251016000086

## 8. cluster:mw:naver-wallapop-correction

### 8.1. NAVER의 왈라팝 인수 관련 최초 공시에서 거래 종결 예정일은 언제였는가?

- Case: case:mw:naver-wallapop:initial-close-date
- Expected: 2025-10-01
- Axes: search_and_extraction / closed / date_lookup / answerable
- Scope: event · Version: original_as_filed
- Documents: exchange_20250918800247

### 8.2. NAVER의 왈라팝 인수 관련 최종 거래 종결일은 언제인가?

- Case: case:mw:naver-wallapop:final-close-date
- Expected: 2026-01-30
- Axes: complex_document_reasoning / closed / correction_aware_lookup / answerable
- Scope: event_revision_chain · Version: latest_in_relation_closure
- Documents: exchange_20250918800247, exchange_20250930800838, exchange_20260130800888

### 8.3. NAVER의 왈라팝 인수 관련 최종 매매대금은 얼마인가?

- Case: case:mw:naver-wallapop:final-amount
- Expected: 902863854765 KRW
- Axes: search_and_extraction / closed / fact_lookup / answerable
- Scope: event_revision_chain · Version: latest_in_relation_closure
- Documents: exchange_20250918800247, exchange_20250930800838, exchange_20260130800888

### 8.4. NAVER의 왈라팝 인수 매매대금은 최초 공시보다 최종 공시에서 얼마 줄었는가?

- Case: case:mw:naver-wallapop:price-decrease
- Expected: 695722410 KRW
- Axes: multiple_retrieval_comparison_calculation / closed / difference / answerable
- Scope: event_revision_chain · Version: compare_original_to_latest
- Documents: exchange_20250918800247, exchange_20260130800888

### 8.5. NAVER의 왈라팝 인수 관련 공시가 최초 제출부터 최종 정정까지 어떻게 바뀌었는지 금액과 거래 종결일 중심으로 설명해줘.

- Case: case:mw:naver-wallapop:correction-summary
- Expected: REQUIRED — 최초 매매대금은 903,559,577,175원이었다.; 거래 종결 예정일은 2025-10-01에서 2026-01-31로 바뀌었다.; 최종 거래 종결일은 2026-01-30이다.; 최종 매매대금은 902,863,854,765원으로 최초보다 695,722,410원 줄었다.
- Axes: complex_document_reasoning / open / history_synthesis / answerable
- Scope: event_revision_chain · Version: full_revision_history
- Documents: exchange_20250918800247, exchange_20250930800838, exchange_20260130800888

### 8.6. NAVER의 왈라팝 인수 최종 매매대금을 매도인별로 나눠 정리해줘.

- Case: case:mw:naver-wallapop:seller-breakdown
- Expected: ABSTAIN — 최종 총액은 있으나 매도인별 배분은 공시에 없다.
- Axes: search_and_extraction / open / single_document_summary / unanswerable
- Scope: event · Version: latest_in_relation_closure
- Documents: exchange_20260130800888

## 9. cluster:mw:naver-business-mix-2023-2024

### 9.1. NAVER의 연결 서비스 매출에서 커머스 비중은 2023년보다 2024년에 높아졌는가?

- Case: case:mw:naver-mix:commerce-increased
- Expected: true — {"2023": "26.4", "2024": "27.2", "change_pp": "+0.8"}
- Axes: multiple_retrieval_comparison_calculation / closed / comparison / answerable
- Scope: company_and_fiscal_year · Version: filed
- Documents: periodic_20240318000844, periodic_20250318000645

### 9.2. NAVER의 연결 서비스 매출 비중에서 2023년 대비 2024년에 가장 크게 늘어난 서비스는 무엇인가?

- Case: case:mw:naver-mix:largest-increase
- Expected: 커머스 / commerce
- Axes: multiple_retrieval_comparison_calculation / closed / ranking / answerable
- Scope: company_and_fiscal_year · Version: filed
- Documents: periodic_20240318000844, periodic_20250318000645

### 9.3. NAVER의 2023년과 2024년 사업보고서를 비교해 연결 서비스 매출 mix가 어떻게 바뀌었는지 설명해줘.

- Case: case:mw:naver-mix:business-change
- Expected: REQUIRED — 서치플랫폼 비중은 37.1%에서 36.8%로 0.3%p 낮아졌다.; 커머스 비중은 26.4%에서 27.2%로 0.8%p 높아졌다.; 핀테크 비중은 14.0%로 같았다.; 콘텐츠 비중은 17.9%에서 16.7%로 1.2%p 낮아졌다.; 클라우드 비중은 4.6%에서 5.3%로 0.7%p 높아졌다.
- Axes: complex_document_reasoning / open / business_change_synthesis / answerable
- Scope: company_and_fiscal_year · Version: filed
- Documents: periodic_20240318000844, periodic_20250318000645

### 9.4. NAVER의 2025년 연간 연결 서비스별 매출 비중과 2024년 대비 변화를 정리해줘.

- Case: case:mw:naver-mix:2025
- Expected: ABSTAIN — miniWorld에는 2025년 연간 사업보고서가 없어 full-year service mix를 확정할 수 없다.
- Axes: complex_document_reasoning / open / business_change_synthesis / unanswerable
- Scope: company_and_fiscal_year · Version: latest_as_of_world_end
- Documents: periodic_20250515001302, periodic_20250814002281, periodic_20251114001436

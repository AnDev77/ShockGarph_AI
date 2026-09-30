# 28~29일차 CPI 주 분석 자산 조정 리뷰

## 변경 구조

- `scripts/evaluate_cpi_asset_groups.py`: SPY·TLT의 5분·30분 가격창과 유효 Kalshi 확률이
  모두 겹치는 사건 수를 별도로 기록한다. 연구 계획의 초기 20건·시험 10건 기준 및 부족분을
  집계만으로 공개한다. 기존 종목별 5건 학습 기준선은 진단용으로 유지한다.
- `tests/integration/test_asset_group_baseline.py`: GLD의 결측과 무관하게 두 자산 공통
  표본을 계산하고, 연구 표본 게이트가 부족함을 검증한다.
- `docs/paper/research-protocol.md`, `docs/paper/analysis-plan.md`: 주 분석을 SPY·TLT로
  제한하고 GLD를 탐색 분석으로 구분한다. FOMC는 별도 사건군으로 후속 확장한다.

## 데이터와 해석

2026-09-30 SIP 사건 진단에서 Kalshi 품질까지 통과한 SPY·TLT 두 구간 공통 사건은
27건이다. 초기 20건 학습 뒤 시험 7건이므로 최소 시험 10건까지 **3건 부족**하다.
이전의 세 ETF 공통 11건보다 많지만, 이는 GLD 결측에 따른 표본 손실을 분리한 결과일 뿐
예측 성능의 개선은 아니다. 이미 결측과 가격 기준선 결과를 확인한 뒤 주 자산을 바꿨으므로
기존 사건에 대한 결과는 탐색적이고, 전향적 또는 외부 표본 검증 없이 논문의 확인적
결론으로 제시하지 않는다. FOMC 사건으로 CPI의 3건 부족분을 채우지 않는다.

## 검증 결과

- `make quality PYTHON=.venv/bin/python`: Ruff 통과, Pyright 오류·경고 0개
- `make test PYTHON=.venv/bin/python`: 115개 통과, 기존 Starlette 경고 1개
- GitHub Actions의 실제 재실행 결과는 푸시 후 확인한다.

## 사용자 점검표

- [ ] Actions 집계의 `primary_cohort.common_eligible_events`가 실제 자료에서 27건인가
- [ ] `research_test_events_available` 7건과 `research_additional_events_needed` 3건인가
- [ ] GLD가 주 분석 수치에 들어가지 않고 탐색 결과로만 남는가
- [ ] 서로 다른 사건을 사용한 종목별 진단 MAE를 직접 우열 비교하지 않는가
- [ ] FOMC의 계약 정의·공식 발표값·시각·유동성·라이선스를 별도로 검토했는가

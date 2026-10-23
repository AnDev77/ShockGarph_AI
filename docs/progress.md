# 프로젝트 진행 기록

마지막 갱신: 2026-10-22. 작업이 끝날 때마다 직전 기록과 달라진 점, 관측한
검증 결과, 여전히 완료하지 못한 조건을 이 문서와 해당 기능 리뷰에 기록한다.
개발 일차와 무관하게 실제 기능을 기준으로 기록한다.
직전 변경은 [초안 PR #4](https://github.com/AnDev77/ShockGarph_AI/pull/4)에 묶었다.

| 순서 | 기능 | 직전 상태 → 이번에 확인된 성과 | 확인 방법과 한계 |
|---|---|---|---|
| 이전 | 가격 기준선과 시점별 스냅샷 | 합성 일별 가격에서 5·20일 위험을 계산하고, 수정된 과거 가격을 예전 예측에 섞지 않는 입력 경로를 만듦 | [가격 버전 리뷰](reviews/price-vintage-asof-review.md). 합성 검증 |
| 이전 | 실제 TLT 단일 이력 탐색 | 가격만 쓴 Ridge·GARCH를 2021~2026년 현재 수정종가 한 벌에서 EWMA와 비교함. 두 기간의 MAE는 EWMA가 낮았음 | [GARCH 탐색 리뷰](reviews/tlt-exploratory-garch-visual-review.md). 시점별 과거 원본과 독립 최종 시험이 아니므로 승인 불가 |
| 이전 | 전통 지표 모델 B의 동일 표본 비교 | 가격 기준선 A, 가격 Ridge B0, 지표 Ridge B1, GARCH를 동일한 날짜·정답에서 비교하는 비공개 경로를 합성 자료로 확인함 | [통계 비교 리뷰](reviews/statistical-risk-comparison-review.md). 실제 TLT+지표 성능은 `HOLD` |
| 이전 | 종목별 첫 화면의 계산 범위 | SPY·TLT를 각각 판단하는 과거 상태 계산기를 만들고, 두 종목은 최초 비중의 기간 총변동률만 합산하도록 정함 | [종목별 화면 리뷰](reviews/asset-first-market-overview-review.md). SPY 실가격·웹 화면·채팅은 없음 |
| **이번** | **일별 금리와 주간 연은 위험지수의 신선도 분리** | 모든 지표에 공통 상한을 적용하던 입력 경로에서 각 지표의 허용 경과시간을 설정할 수 있게 변경. 어떤 지표의 결측·지연으로 B 행이 빠졌는지도 보고함 | [지표 신선도 리뷰](reviews/indicator-freshness-gate-review.md). 지표 실자료를 새로 수집하거나 성능을 입증한 것은 아님 |
| **신규** | **지표 수집 시각을 반영한 비공개 비교** | 기존 게시 시각만 확인하던 비교에서 수집 시각을 필수로 받고 더 늦은 시각부터 지표를 사용함. 구형 파일은 명시적인 탐색 옵션에서만 허용 | [지표 수집 시각 리뷰](reviews/indicator-capture-provenance-review.md). 수신 사실의 독립 증거·실가격·실지표 공통 이력은 여전히 없음 |
| 이전 | 키 없는 재무부 금리 원본 수집 | 공개 재무부 월별 XML을 HTTP 수신 뒤 UTC 시각·원본 바이트·해시와 함께 보관하는 수집기와 명령을 추가 | [재무부 수집 리뷰](reviews/treasury-yield-collection-review.md). 이 환경에서 외부 도메인 조회는 실패함 |
| **추가** | **재무부 금리 빈티지의 B 입력 연결과 TLT 커버리지** | 직전에는 원본 저장만 가능했음 → 이제 보관 XML·해시를 재검사해 수신 순서별 날짜 금리를 B의 `UST10Y_PAR` 입력으로 쓰고, 가격 이력과 겹치는 날짜·수신 이후 세션을 보고할 수 있음 | [빈티지 연결 리뷰](reviews/treasury-vintage-risk-panel-review.md). 153개 합성 시험 통과. 실제 재무부 응답 미수신, TLT 가격의 당시 버전 미확보로 성능 `HOLD` |
| **실수집** | **재무부 공식 XML 실수신과 TLT 날짜 겹침 측정** | HTTP 접근 실패 판정을 재검토하고 SOCKS 의존성을 추가. `curl` 경유 1건과 공식 Python 수집 명령 1건으로 2026-10 월별 XML을 실제 수신·보관. TLT 1,253개 세션 중 같은 관측 날짜 11개를 찾았지만 첫 수신 이후 가격 세션은 0개 | [실수집 리뷰](reviews/treasury-live-ingestion-review.md). 과거 관측일이 같다고 당시 예측에 쓸 수 있던 것은 아님. 실 A/B `HOLD` |
| **추가** | **Alpaca SIP 가격 원본과 TLT·SPY 스냅샷 경로** | 직전에는 공급원 없는 TLT 수정종가 단일 파일만 있었음 → 키가 주입되면 Alpaca의 원본·조정 일봉을 각각 보관하고 TLT·SPY 전체 가격 CSV와 원본 해시 manifest를 생성해 기존 시점별 위험 입력 형식으로 검사할 수 있음 | [Alpaca 가격 리뷰](reviews/alpaca-sip-price-snapshots-review.md). 전체 157개 시험 통과. 로컬에는 키가 없어 합성으로 검증했으며 실제 응답은 아래 Actions 작업에서 확인 |
| **실수집** | **GitHub Actions의 Alpaca 비밀 변수 연결과 TLT·SPY 커버리지** | 키 두 개를 Actions에서 사용하고 최근 날짜형 SIP 403을 명시적 UTC 종료 시각으로 해결. 실제 SIP 응답으로 TLT·SPY 각각 704거래일을 수집해 원본·조정본, 날짜 완전성을 확인 | [Alpaca 가격 리뷰](reviews/alpaca-sip-price-snapshots-review.md) 및 [실행](https://github.com/AnDev77/ShockGarph_AI/actions/runs/39742059555). 원본·CSV는 일회성 러너에서 삭제됨. 과거 시점별 보관본, 재배포 권리, A/B 성능은 여전히 `HOLD` |
| **탐색 실분석** | **TLT·SPY 가격 기준선 종목별 비교** | 직전에는 실제 가격의 거래일 수만 확인 → 수집 직후 manifest·CSV 해시를 다시 검사하고 각 종목의 최근 변동성·EWMA·GARCH·가격 Ridge를 동일한 5·20일 정답에서 비교. TLT 5일 Ridge 0.1865%p·20일 GARCH 0.0846%p, SPY 5일 Ridge 0.2297%p·20일 Ridge 0.1725%p가 이 평가 구간의 최저 MAE | [종목별 가격 비교 리뷰](reviews/alpaca-price-only-comparison-review.md), [실행](https://github.com/AnDev77/ShockGarph_AI/actions/runs/39874550442). 기존 보고서의 20일 9개는 시작일 완전 묶음 수였으며 실제 비중첩 미래 구간의 최대 개수는 10개다. 현재 조정 이력의 과거 재계산. 시점별 A/B 판정은 `HOLD` |
| **표현 수정** | **비중첩 평가 구간 수 구분** | 직전에는 182개 시작일을 20개씩 내림해 9개를 비중첩 구간으로 잘못 표시 → 연속 시작일에서 미래 정답이 겹치지 않게 선택할 수 있는 10개와 보수적 완전 묶음 9개를 별도 출력. 기존 MAE와 모델 판정 수식은 그대로 | [구간 수 리뷰](reviews/nonoverlapping-holdout-count-review.md). 구간의 시간적 상관과 독립 시험 부족은 여전히 남음 |

## 현재 제품 판정

- TLT 5·20일 **시점별 실제 A/B 성능은 `HOLD`**다. 당시 이용 가능한 가격 버전·
  지표 게시 시각·허용된 사용 범위와 새 독립 시험 기간을 확보해야 한다.
- 주간 지수 `NFCI_RISK` 등은 시장 전체 상태의 후보 입력이다. SPY·TLT 각각에
  유용한지는 같은 날짜의 가격 전용 B0와 지표 추가 B1으로 별도 판정한다.
- Actions에서는 SPY 실가격을 수신했지만 영속 보관하지 않았다. 공개 웹 화면 및 채팅 서버는 없다. Kalshi 계약 확률은
  특정 계약의 당시 기대를 설명하는 별도 자료이며 B 입력으로 사용하지 않는다.

## 다음 기록 규칙

새 작업 리뷰에는 **직전 상태 → 바뀐 동작 → 실제 검증 수치 → 남은 게이트**를
적는다. 작업 중 장애가 생기면 [트러블슈팅 기록](troubleshooting.md)에 발생 증상,
원인, 해결/우회, 확인 결과와 남은 한계를 추가한다. 합성 자료의 오차와 실제
투자상품의 평가 결과를 구분해 표시한다.

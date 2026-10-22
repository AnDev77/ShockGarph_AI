# 트러블슈팅 기록

마지막 갱신: 2026-10-22. 재현 가능한 증상과 그때 확인한 원인만 기록한다.
해결되지 않은 데이터·권리 문제는 해결로 표시하지 않는다. 자세한 당시 기록은
각 기능 리뷰에 연결한다.

## 가격·지표 데이터

| 증상 | 확인한 원인 | 적용한 조치와 상태 | 근거 |
|---|---|---|---|
| TLT 20일 예측 성능을 실제로 판정할 수 없었음 | 처음에는 실제 가격 원본이 없었고, 이후 구한 현재 수정종가 한 벌에는 과거 일별 수정 버전·수신 시각이 없음. 신규 독립 시험 기간도 부족함 | 가격 전체 스냅샷·시점별 정답 계약과 `HOLD` 게이트를 추가. **실자료 확보 문제는 미해결** | [실증 가능성](reviews/prediction-data-feasibility-review.md), [가격 버전](reviews/price-vintage-asof-review.md) |
| 뒤늦게 수정된 가격을 과거 예측 입력으로 오인할 수 있음 | 수정종가는 배당 등으로 이전 날짜 값도 바뀔 수 있음 | 예측 당시 보관한 완전한 가격 파일 한 벌을 선택하고, 이후 받은 정답은 별도 파일에서 계산함. 합성 시험으로 누수 차단을 확인함 | [가격 버전](reviews/price-vintage-asof-review.md) |
| 2025-01-09에 존재하지 않은 미국 주식 세션이 생김 | 연간 예정 달력만 사용하면 임시 휴장 반영이 누락됨 | Nasdaq 추가 공지를 대조해 2024~2026년 달력에 반영하고, 가짜 휴장일 가격을 거부함 | [다년 거래일](reviews/multiyear-nasdaq-risk-calendar-review.md) |
| 일별 DGS10과 주간 연은 위험지수에 같은 경과시간을 적용하면 어느 한쪽이 불필요하게 결측 또는 너무 오래된 값이 됨 | B 패널의 `max_indicator_age`가 모든 지표에 공통이었음 | **이번 작업:** 지표별 상한과 어떤 지표에서 행이 빠졌는지 출력 추가. 정해진 게시 시각을 역산하지 않으며 실자료 유효성은 계속 미확인 | [지표 신선도](reviews/indicator-freshness-gate-review.md) |
| FRED의 관측 날짜를 예측 당시 게시 시각으로 오인할 수 있음 | 관측일/빈티지 날짜는 과거 일중 수신을 증명하지 않음 | 입력 CSV의 UTC `observed_at`·`available_at`을 필수로 두고 늦게 공개된 행은 배제. **과거 실제 게시 시각 증거는 미확보** | [A/B 홀드아웃](reviews/traditional-risk-ab-holdout-review.md) |
| 지표가 API에 게시되었지만 우리 서버의 수집 전 예측에 사용될 수 있음 | 기존 B 입력은 공급원의 게시 시각만 받고 실제 수신 시각을 따로 검사하지 않음 | 기본 CLI에 `captured_at`을 필수로 하고 수신 시각부터 사용. 입력 CSV의 시각은 외부 증명이 아니므로 실제 수신 원본 확보는 **미해결** | [수집 시각 게이트](reviews/indicator-capture-provenance-review.md) |
| Kalshi 공개 조회가 403·시간 초과로 중단됨 | 당시 원격 서비스와 실행 환경의 어느 쪽 때문인지 확정하지 못함 | 운영 호환 URL과 재시도 경로로 2026-09-26 전체 CPI 감사에서 접근 오류 0건 확인. 특정 실행 환경의 안정적 접근과 실시간 운영은 별도 문제 | [초기 접근](reviews/day-07-08-review.md), [재시도 결과](cpi-coverage-review.md) |
| CPI 계약의 55개 결과를 모두 평가할 수 없음 | 20개는 유효 캔들이 없고 6개는 오래된 호가여서 평가 입력 품질 조건에 미달 | 확률을 보간하거나 결과값으로 채우지 않고 유효 29개·기준과 비교 가능 24개로 한정. **ETF 위험 검증 표본은 확보하지 못함** | [CPI 커버리지](cpi-coverage-review.md) |

## 모델·제품 판단

| 증상 | 확인한 원인 | 적용한 조치와 상태 | 근거 |
|---|---|---|---|
| Kalshi CPI 표본으로 ETF 위험을 검증하기 어려움 | 유효 계약·발표 표본이 제한되고 계약 가격이 ETF 변동성 정답이 아님 | 계약의 당시 기대는 설명 자료로 분리하고, 가격 기준선 A 대 전통 정보 B를 먼저 비교 | [CPI 조사](cpi-coverage-review.md), [기대 맥락 분리](reviews/kalshi-expectation-context-review.md) |
| 더 복잡한 모형이면 낫다는 주장을 할 수 없음 | 현재 수정종가 한 벌의 비공개 탐색에서 Ridge·GARCH의 5·20일 MAE가 EWMA보다 큼. 5일 QLIKE 등 일부 지표 판단은 다름 | MAE와 QLIKE를 함께 보고하고, 이미 본 구간은 독립 시험으로 재사용하지 않음. B의 실제 증분 효과는 `HOLD` | [GARCH 탐색](reviews/tlt-exploratory-garch-visual-review.md) |
| 첫 화면의 공동 분석 결과가 사용자의 종목별 판단을 흐림 | 사용자 피드백에서 SPY·TLT 각각의 상태가 우선이라고 명시됨 | 두 종목의 과거 위험·변화를 각각 계산하고 합산은 최초 비중의 기간 총변동률로 축소 | [종목별 화면](reviews/asset-first-market-overview-review.md) |

## 작업 환경

2026-10-22: 가상환경 생성 뒤 첫 `make test`는 `pygments.formatters.terminal`,
첫 `make quality`는 `ruff._find_ruff`가 없어 실행 전 실패했다. 기존 패키지의
불완전한 설치가 남아 있어 `uv sync --reinstall --extra dev --extra viz`로 강제
재설치했다. 재설치 뒤 전체 시험과 정적 검사를 다시 실행한 결과는
[수집 시각 리뷰](reviews/indicator-capture-provenance-review.md)에 기록한다.

| 증상 | 확인한 원인 | 적용한 조치와 상태 | 근거 |
|---|---|---|---|
| `.venv/bin/python`을 실행할 수 없어 첫 테스트가 시작되지 않음 | 전달된 가상환경의 실행 파일이 없었음. `uv run --offline`은 필요한 패키지가 캐시에 없어서 새 환경을 만들고 설치에 실패함 | `uv sync --extra dev --extra viz`로 개발·그래프 의존성을 다시 설치. 이후 `make test`와 `make quality`로 확인 | [지표 신선도](reviews/indicator-freshness-gate-review.md) |
| 새 환경에서 Pyright가 `matplotlib`을 찾지 못함 | 처음 복구 명령은 `dev` 추가 항목만 설치하고, 저장소의 선택적 `viz` 추가 항목은 빠뜨림 | `viz`까지 동기화해 모듈 해석 오류를 제거. 기존 저장소 의존성 선언은 그대로 유지 | [지표 신선도](reviews/indicator-freshness-gate-review.md) |
| 로컬 커밋을 `git push`로 GitHub에 업로드할 수 없었음 | 이 작업 환경의 Git 원격에 GitHub HTTPS 인증 정보가 없어 사용자명을 읽지 못함 | 이미 승인된 GitHub 연결로 원격 기존 브랜치에서 새 기능 브랜치를 만들고, 로컬과 **동일한 파일 트리 해시**를 가진 커밋을 작성해 초안 PR을 열었음. 로컬·원격의 커밋 ID는 다르므로 후속 개발에서는 원격 트리를 대조해야 함 | [진행 기록](progress.md) |

새 오류가 발생하면 해당 행의 해결 상태와 실제 재실행 결과를 갱신한다.

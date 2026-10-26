# 트러블슈팅 기록

마지막 갱신: 2026-10-22. 재현 가능한 증상과 그때 확인한 원인만 기록한다.
해결되지 않은 데이터·권리 문제는 해결로 표시하지 않는다. 자세한 당시 기록은
각 기능 리뷰에 연결한다.

## 가격·지표 데이터

| 증상 | 확인한 원인 | 적용한 조치와 상태 | 근거 |
|---|---|---|---|
| TLT 20일 예측 성능을 실제로 판정할 수 없었음 | 처음에는 실제 가격 원본이 없었고, 이후 구한 현재 수정종가 한 벌에는 과거 일별 수정 버전·수신 시각이 없음. 신규 독립 시험 기간도 부족함 | 가격 전체 스냅샷·시점별 정답 계약과 `HOLD` 게이트를 추가. **실자료 확보 문제는 미해결** | [실증 가능성](reviews/prediction-data-feasibility-review.md), [가격 버전](reviews/price-vintage-asof-review.md) |
| Alpaca 키가 있다고 알려졌으나 이 실행 환경의 첫 가격 수집은 시작되지 않음 | 저장소 `.env.example`은 값 없는 예시이고 현재 프로세스의 `APCA_API_KEY_ID`·`APCA_API_SECRET_KEY`도 비어 있음. GitHub 비밀값은 현재 실행 셸로 자동 전달되지 않음 | 키 값은 출력·커밋하지 않고 두 환경 변수의 존재 여부만 확인. 로컬은 `missing_credentials`를 반환했으나 Actions에서 SIP 실수집은 성공. 수집기와 기존 스냅샷 연결은 합성 응답으로도 검증 | [Alpaca 가격](reviews/alpaca-sip-price-snapshots-review.md) |
| GitHub Actions에 등록된 키를 로컬 셸에서 사용할 수 없음 | Actions 비밀 변수는 워크플로 실행 중에만 전달됨 | 기능 브랜치 수집 워크플로에서 두 변수를 읽어 실제 SIP 요청에 성공함. 공개 저장소의 아티팩트에는 원본 가격을 올리지 않음 | [실수집](https://github.com/AnDev77/ShockGarph_AI/actions/runs/39742059555) |
| Alpaca 일봉의 마지막 거래일이 누락되거나 SIP 403이 발생 | 일봉 UTC 시각은 미국 현지 자정인 04:00/05:00이며 날짜형 상한과 무료 SIP의 최근 범위 제한이 함께 작용함 | 다음 날짜형 상한은 최근 SIP 403으로 실패. 마지막 거래일의 UTC `23:59:59Z`로 명시해 재실행했고 TLT·SPY 각 704거래일 수집 성공 | [실수집](https://github.com/AnDev77/ShockGarph_AI/actions/runs/39742059555) |
| Actions에서 Alpaca 가격 수집 HTTP 403 | 두 비밀 변수는 존재하고 의존성 설치는 완료했으나 SIP 요청이 거절됨. 인증 쌍의 종류·계정 권한·SIP 피드 중 어느 단계 문제인지는 미확인 | 오래된 하루의 IEX/SIP 요청 결과를 숫자 상태 코드만 남기는 진단을 추가함. 실제 응답을 받아 원인을 구분하기 전까지 실가격 확보로 표시하지 않음 | [실행 #39740895747](https://github.com/AnDev77/ShockGarph_AI/actions/runs/39740895747) |
| 최근 SIP 요청만 403 | 오래된 IEX·SIP 하루 및 넓은 SIP 기간은 모두 200, 현지 전일~오늘 날짜 범위만 403 | API 키는 과거 Alpaca 데이터에 유효함. 최근 날짜형 상한을 마지막 거래일의 명시적 UTC 시각으로 변경해 전체 수집 성공 | [실행 #39742059555](https://github.com/AnDev77/ShockGarph_AI/actions/runs/39742059555) |
| 로컬 `make quality`가 Ruff 실행 시 segmentation fault로 멈춤 | 기존 가상환경의 Ruff 실행 파일이 비정상 종료했으며 정확한 바이너리 손상 원인은 미확인 | `uv pip install --python .venv/bin/python --reinstall 'ruff>=0.9,<1'`로 개발 도구를 다시 설치. Ruff·Pyright와 전체 158개 시험을 재실행해 통과함. 제품 코드 오류로 간주하지 않음 | [종목별 가격 비교](reviews/alpaca-price-only-comparison-review.md) |
| 실제 Alpaca 현재 이력으로 모델 오차는 계산되지만 과거 시점별 성능은 판정 불가 | 2026-10-23 수집본 하나에는 2024~2026년의 각 날짜에 보였던 조정가격 버전이 없고 Actions 러너의 비공개 원본도 작업 종료 후 삭제됨 | 연구 전용 지표로 5·20일 종목별 오차·비중첩 창 개수만 보고하고 제품 성능 플래그를 false로 유지함. 비공개 영속 보관과 이후 새 표본을 확보하기 전에는 시점별 A/B를 `HOLD`로 둠 | [탐색 실분석](reviews/alpaca-price-only-comparison-review.md) |
| 뒤늦게 수정된 가격을 과거 예측 입력으로 오인할 수 있음 | 수정종가는 배당 등으로 이전 날짜 값도 바뀔 수 있음 | 예측 당시 보관한 완전한 가격 파일 한 벌을 선택하고, 이후 받은 정답은 별도 파일에서 계산함. 합성 시험으로 누수 차단을 확인함 | [가격 버전](reviews/price-vintage-asof-review.md) |
| 2025-01-09에 존재하지 않은 미국 주식 세션이 생김 | 연간 예정 달력만 사용하면 임시 휴장 반영이 누락됨 | Nasdaq 추가 공지를 대조해 2024~2026년 달력에 반영하고, 가짜 휴장일 가격을 거부함 | [다년 거래일](reviews/multiyear-nasdaq-risk-calendar-review.md) |
| 일별 DGS10과 주간 연은 위험지수에 같은 경과시간을 적용하면 어느 한쪽이 불필요하게 결측 또는 너무 오래된 값이 됨 | B 패널의 `max_indicator_age`가 모든 지표에 공통이었음 | **이번 작업:** 지표별 상한과 어떤 지표에서 행이 빠졌는지 출력 추가. 정해진 게시 시각을 역산하지 않으며 실자료 유효성은 계속 미확인 | [지표 신선도](reviews/indicator-freshness-gate-review.md) |
| FRED의 관측 날짜를 예측 당시 게시 시각으로 오인할 수 있음 | 관측일/빈티지 날짜는 과거 일중 수신을 증명하지 않음 | 입력 CSV의 UTC `observed_at`·`available_at`을 필수로 두고 늦게 공개된 행은 배제. **과거 실제 게시 시각 증거는 미확보** | [A/B 홀드아웃](reviews/traditional-risk-ab-holdout-review.md) |
| 지표가 API에 게시되었지만 우리 서버의 수집 전 예측에 사용될 수 있음 | 기존 B 입력은 공급원의 게시 시각만 받고 실제 수신 시각을 따로 검사하지 않음 | 기본 CLI에 `captured_at`을 필수로 하고 수신 시각부터 사용. 입력 CSV의 시각은 외부 증명이 아니므로 실제 수신 원본 확보는 **미해결** | [수집 시각 게이트](reviews/indicator-capture-provenance-review.md) |
| 공개 재무부 금리 API의 실제 수집이 처음에는 실패함 | 이 환경의 SOCKS 프록시를 쓰는 `httpx`에 `socksio`가 없었고, 직접 연결에서는 DNS가 실패함 | `curl`의 공식 URL HTTP 200을 확인한 뒤 `httpx[socks]` 의존성을 추가. 기존 Python 공식 수집 명령으로 2026-10 XML을 실제 수신해 14개 관측일을 원본 저장함. **연결 문제 해결**, 과거 게시 시각 증거와 TLT 당시 가격 버전은 미해결 | [재무부 실수집](reviews/treasury-live-ingestion-review.md) |
| 재무부 XML의 날짜를 일중 관측 시각으로 치환하면 예측 시점과 신선도를 잘못 계산함 | 원천은 날짜만 주고 게시 시각을 주지 않음 | 날짜 필드와 UTC 수신 시각을 분리해 수신 전 예측을 배제하고, 날짜 시작은 보수적 신선도 기준으로만 사용. 이 기준은 실제 일중 관측 시각이 아니며 공식 응답 검증은 **미해결** | [빈티지 연결](reviews/treasury-vintage-risk-panel-review.md) |
| 잘못된 월·중복 날짜가 포함된 XML도 원본 저장에 남을 수 있었음 | 기존 수집기는 저장 뒤 날짜별 금리를 검사했음 | 원본 내용 검증을 저장 전에 옮기고 잘못된 입력에서 보관 파일 0건을 합성 시험으로 확인함. 실제 HTTP 연결 문제는 **미해결** | [빈티지 연결](reviews/treasury-vintage-risk-panel-review.md) |
| Kalshi 공개 조회가 403·시간 초과로 중단됨 | 당시 원격 서비스와 실행 환경의 어느 쪽 때문인지 확정하지 못함 | 운영 호환 URL과 재시도 경로로 2026-09-26 전체 CPI 감사에서 접근 오류 0건 확인. 특정 실행 환경의 안정적 접근과 실시간 운영은 별도 문제 | [초기 접근](reviews/day-07-08-review.md), [재시도 결과](cpi-coverage-review.md) |
| CPI 계약의 55개 결과를 모두 평가할 수 없음 | 20개는 유효 캔들이 없고 6개는 오래된 호가여서 평가 입력 품질 조건에 미달 | 확률을 보간하거나 결과값으로 채우지 않고 유효 29개·기준과 비교 가능 24개로 한정. **ETF 위험 검증 표본은 확보하지 못함** | [CPI 커버리지](cpi-coverage-review.md) |

## 모델·제품 판단

| 증상 | 확인한 원인 | 적용한 조치와 상태 | 근거 |
|---|---|---|---|
| 20일 평가의 비중첩 미래 구간을 9개라고 설명함 | `182 // 20`은 시작일의 완전한 20개 묶음만 세며, 실제로는 182개의 연속 시작일에서 1·21·…·181번째의 미래 정답 10개를 겹침 없이 선택 가능 | 탐색 보고서에 실제 비중첩 최대 10개와 기존 보수적 묶음 9개를 따로 표시. 두 숫자 모두 독립적인 시장 실험 횟수로 해석하지 않음 | [구간 수 리뷰](reviews/nonoverlapping-holdout-count-review.md) |
| 구간 수와 재표집 이름만으로 오차 해석의 근거를 확인하기 어려움 | 미래 20일 정답의 공유 수익률과 오차 차이의 공분산 항, 합성 수치 예시 및 원 논문 연결이 빠져 있었음 | [방법론](daily-risk-methodology.md#미래-정답의-겹침과-평가-불확실성)에 공식·가상 수익률·구현 설정·출처를 추가. 실제 오차 자기상관과 블록 길이의 적절성은 별도로 확인해야 함 | [구간 수 리뷰](reviews/nonoverlapping-holdout-count-review.md) |
| 매일 평가한 20일 MAE만으로 시작일 선택·블록 길이에 따른 결론 차이를 알 수 없음 | 기존 보고에는 평균과 길이 `h` 블록 구간만 있고 날짜별 짝지은 오차의 연속성 검사가 없었음 | 날짜별 GARCH·Ridge와 EWMA 오차 차이를 같은 날짜에서 비교해 `h`개 모든 시작 위치와 `2h` 블록 민감도, 1일 시차 상관을 집계. 실제 SIP 수집 뒤 TLT 20일 Ridge의 20개 시작 위치 중 음수가 9개뿐임을 확인. 성능 승인이나 권리 확보와는 별개 | [겹침 진단](reviews/overlap-diagnostics-review.md) |
| 이전 Yahoo 탐색의 가격 모형 열세가 현재 프로젝트 전체의 모델 탈락처럼 읽힘 | 모델 설계 문서의 마지막 판단 문장이 후속 Alpaca SIP 다른 기간 탐색을 반영하지 않음 | 공급원·기간별 결과를 분리하고 어느 쪽도 시점별 독립 성능 평가가 아님을 명시. 실제 거시 B1의 효과는 여전히 `HOLD` | [현대적 모델 단계](reviews/modern-risk-model-research-stage-review.md) |
| GJR가 모든 ETF에서 대칭 GARCH보다 개선된다는 가정은 실제 탐색과 맞지 않음 | TLT의 학습된 비대칭 계수가 0인 반면 SPY는 0.215117. SPY 20일의 겹친 미래 구간을 고려한 오차 차이의 블록 구간은 0을 포함 | 종목별 계수·5/20일 MAE·길이 `h`와 `2h` 블록을 나눠 보고, TLT에는 개선 없음, SPY 20일에는 우위 미확정으로 기록. 이미 본 표본을 독립 시험으로 재사용하지 않음 | [비대칭 위험](reviews/gjr-garch-price-risk-review.md) |
| SPY 20일의 전체 MAE 개선만 보면 월별 편차가 가려짐 | 같은 평가 기간의 9개 시작 월 중 개선은 4개월이고, 4월 시작일이 전체 오차 차이 합의 약 80%에 기여 | 같은 예측 시작일의 월별 MAE 차이와 4월 제외 단순 재집계를 추가. 20일 우위는 계속 보류하고 월별 결과를 독립 실험 또는 시장 국면 모형의 학습 근거로 사용하지 않음 | [월별 오차](reviews/monthly-risk-error-stability-review.md) |
| 비대칭 모형을 더 자주 재학습하면 위험 예측이 개선될 것이라는 예상이 실제 탐색과 맞지 않음 | SPY 5일 고정 GJR MAE 0.2155%p, 월초 재학습 0.2175%p. 20일도 고정 0.1673%p, 월초 0.1677%p | 추가 이득을 주장하지 않고, 월초 재학습 GJR와 대칭 GARCH, 고정 GJR를 같은 시작일에서 비교했다. 예측 당시 가격 빈티지·새 독립 기간 미확보로 채택 보류 | [월초 재학습](reviews/monthly-garch-refit-stability-review.md) |
| 가격 수집의 매 실행마다 원본이 사라져 사전 예측을 나중에 채점할 수 없음 | 기존 Actions 러너의 `data/raw`와 CSV가 일회성이고 비공개 영속 버킷 설정이 아직 없음 | 원본·정규화 파일·manifest·사전 예측을 해시로 묶어 조건부 S3 쓰기를 수행하는 수동 작업을 추가. 합성 S3 시험은 성공했지만 **실제 버킷 설정과 원격 저장은 미해결** | [사전 보관](reviews/private-forward-price-archive-review.md) |
| 보관 직후 성공 메시지만으로 예측이 실제 개장 전에 S3에 기록됐는지 확인하기 어려움 | 이전에는 예측의 논리적 시각만 기록하고 최종 index의 S3 서버 기록 시각과 전체 원본을 외부에서 다시 읽는 명령이 없었음 | 저장 직후와 별도 읽기 명령에서 `LastModified`·객체 전체 바이트·해시를 감사한다. 합성 변조·늦은 index 시험은 통과. **실제 버킷 접근과 원격 실행은 미확인** | [원격 감사](reviews/private-forward-readback-audit-review.md) |
| AWS 전용 보관 경로가 사용자의 지속 무료 운영 조건에 맞지 않음 | 기존 CLI가 S3 Public Access Block과 SSE-S3 요청을 필수로 사용했고 기간 만료형 AWS 무료 플랜을 가정함 | R2 전용 엔드포인트·기본 암호화·조건부 쓰기로 변경하고 전용 버킷의 8GB·실행 4MB 상한을 업로드 전 검사. 합성 시험은 통과해도 **실제 R2 연결·결제 조건은 미확인**, 계정 전체 0원은 보장하지 않음 | [R2 전환](reviews/r2-private-vintage-budget-review.md) |
| 늦은 시각에 수집한 전일 가격을 장중이나 장 마감 이후의 수익률까지 포함하는 사전 예측으로 오인할 수 있음 | 기존 탐색 워크플로는 미국 시간상 다음 세션 개장 후에 실행되기도 했음. 종가 전이라는 조건만으로는 일부 수익률이 이미 발생한 구간을 막지 못함 | 원본 저장을 마친 시각이 다음 정규장 개장 최소 1시간 이전일 때에만 사전 예측을 남김. 늦으면 원본만 저장하고 예측 0개; 합성 시험으로 확인 | [사전 보관](reviews/private-forward-price-archive-review.md) |
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
| 새 GJR 시험을 처음 정적 검사할 때 Optional 값의 대소 비교에서 Pyright 오류 1건 | `gjr_volatility`는 최적화 실패 시 `None`일 수 있는데 시험이 곧장 `> 0`으로 비교 | 시험에서 `None` 여부를 먼저 확인하도록 수정. Ruff 위반 0건, Pyright 오류·경고 0건과 전체 163개 시험으로 다시 검증 | [비대칭 위험](reviews/gjr-garch-price-risk-review.md) |
| 월별 집계의 첫 통합 시험에서 미채점 끝부분이 `None`으로 표시됨 | 계산은 20일 진단의 최소 블록 수 부족 상태에도 끝부분의 20개 미래 정답 부재를 표시해야 하는데, 새 출력은 탐색 상태에서만 값을 내도록 작성됨 | 상태와 무관하게 홀드아웃 가격 행 수에서 채점 시작일 수를 빼도록 수정. 합성 20일 제한 상태의 통합 시험에서 끝부분 20일을 재확인 | [월별 오차](reviews/monthly-risk-error-stability-review.md) |
| 월초 재학습 부족 표본 시험에서 모든 기간이 차단될 것으로 예상했으나 5일은 채점 가능했음 | 시험의 20개 홀드아웃 가격 중 5일은 미래 구간 15개·완전 묶음 3개가 남고, 20일은 0개다 | 시험에서 20일 차단만 정확히 검사하고 5일은 정상적으로 수행. 전체 165개 시험을 다시 실행해 통과 | [월초 재학습](reviews/monthly-garch-refit-stability-review.md) |
| 원본 JSON 파일에 공백 한 글자를 덧붙여도 초기 보관 시험이 통과 | 기존 보관 검사는 파싱한 payload 해시만 검증하고 봉투 파일의 원래 바이트는 재검사하지 않았음 | 저장소의 정규 JSON 인코딩과 파일 바이트를 직접 대조해 추가 바이트를 거절. 변조 시 원격 객체 0건인 통합 시험으로 확인 | [사전 보관](reviews/private-forward-price-archive-review.md) |
| 로컬 커밋을 `git push`로 GitHub에 업로드할 수 없었음 | 이 작업 환경의 Git 원격에 GitHub HTTPS 인증 정보가 없어 사용자명을 읽지 못함 | 이미 승인된 GitHub 연결로 원격 기존 브랜치에서 새 기능 브랜치를 만들고, 로컬과 **동일한 파일 트리 해시**를 가진 커밋을 작성해 초안 PR을 열었음. 로컬·원격의 커밋 ID는 다르므로 후속 개발에서는 원격 트리를 대조해야 함 | [진행 기록](progress.md) |

새 오류가 발생하면 해당 행의 해결 상태와 실제 재실행 결과를 갱신한다.

## R2 최초 원격 실행 대기 (2026-10-26)

- 증상: 기존 `workflow_dispatch`는 기능 브랜치에만 존재하여 기본 브랜치의 Actions 목록에서 바로 실행할 수 없었다.
- 원인: GitHub 수동 실행의 기본 브랜치 등록 조건과 초안 PR의 분리 상태.
- 조치: 기능 브랜치의 워크플로 파일 변경 시에만 실행되는 `push` 트리거를 추가했다. 새 실행은 구성 검사, Alpaca 수집, R2 보관과 읽기 재검증, TLT·SPY 탐색 분석을 순서대로 수행한다.
- 검증 상태: 원격 실행 로그 확인 전에는 해결로 표시하지 않는다. 인증값은 출력하거나 커밋하지 않는다.

## R2 계정 식별자 형식 오류와 재시도 (2026-10-26)

- 증상: [첫 Actions 실행](https://github.com/AnDev77/ShockGarph_AI/actions/runs/40248276178)의 보관 단계가 `private_archive_not_configured`로 중지됐다.
- 원인: `SHOCKGRAPH_R2_ACCOUNT_ID`에 32자리 계정 식별자가 아닌 다른 형식의 값이 들어 있었다.
- 조치: 저장소 Variables의 값을 사용자가 바로잡고 동일 실행의 실패 작업을 재시도했다.
- 검증: 2차 시도에서 설정 검사·원격 저장·읽기 재검증·가격 탐색 분석 단계가 모두 성공했다. 첫 실행 로그에 기존 변수 값이 남을 수 있으므로 해당 실행의 로그 접근 범위를 별도 확인해야 한다.

## 빈 wheel 산출물 (2026-10-26)

- 증상: 최초 wheel 빌드는 성공했지만 압축 파일에는 Python 소스 없이 `dist-info` 메타데이터만 들어 있었다.
- 원인: `pyproject.toml`에 `packages = []`가 지정되어 빌드 과정이 모든 패키지를 제외했다.
- 조치: 여섯 소스 디렉터리를 패키지 이름과 명시적으로 연결하고 wheel 내부 필수 파일을 검사하는 스크립트와 PR 게이트를 추가했다.
- 검증: 로컬 재빌드에서 필수 소스 7개를 확인했다. [수정된 PR 게이트](https://github.com/AnDev77/ShockGarph_AI/actions/runs/40249457880)에서도 필수 소스 7개를 확인했다.

## PR 게이트의 Pyright 선택 의존성 오류 (2026-10-26)

- 증상: [첫 PR 게이트](https://github.com/AnDev77/ShockGarph_AI/actions/runs/40249311447)에서 빌드·산출물·Ruff는 통과했지만 Pyright가 `matplotlib` import 3건을 찾지 못해 실패했다.
- 원인: 로컬 `.venv`에 있던 시각화 선택 의존성과 `pyproject.toml`의 `.venv` 설정을 CI의 전역 Python 설치가 재현하지 못했다.
- 조치: CI에 `.venv`를 만들고 `dev,viz` 선택 의존성을 설치하며 모든 검사를 같은 인터프리터로 실행하도록 수정했다.
- 검증: 수정된 PR 실행에서 Pyright 오류·경고 0건과 전체 175개 시험 통과.

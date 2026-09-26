# 9~10일차 Kalshi CPI 데이터 접근과 실험 경로 리뷰

작성일: 2026-09-23

## 이번 작업의 판단

Kalshi CPI 시리즈 `KXCPI`의 데이터 부재는 확인되지 않았다. 2026-09-17 저장소의
[데이터 가용성 기록](../data-feasibility.md)에 당시 63개의 결과 확정 CPI 발표,
508개 결과 확정 계약, 과거 **일별 캔들** 공개 GET 성공이 남아 있다.
다만 현재 작업 환경에서는 Kalshi 도메인의 상태 조회부터 제대로 열리지 않아
그때의 응답을 재확인할 수 없었다. 발표 직전 1분 캔들·유효한 양방향 호가가
과거 63건에 걸쳐 존재하는지도 확인되지 않았다.

## 변경 코드 구조

| 경로 | 작업 |
|---|---|
| `scripts/probe_cpi_coverage.py` | 상태·시리즈 경로 연결 확인, 2026년 8월 CPI 계약 하나의 발표 5분 전 1분 캔들 조회, 발표 이전·거래량·호가·스프레드·15분 신선도 점검 |
| `tests/integration/test_event_research.py` | 발표 후 캔들·역전 호가·무거래 캔들 제외, 지정된 과거 계약 조회와 경계시각, 경로 입력 검증 |
| `docs/kalshi-cpi-access-methods.md` | 과거 근거와 이번 연결 장애 구분, 데이터 가용성 4단계별 연구 질문·조건·보류 기준 |
| `docs/cpi-coverage-review.md` | 상세 점검 문서 연결 |

## 실제 연결 시도

1. 기본 URL에 대해 프록시 적용과 직접 연결 각각 공개 GET 6경로를 제한시간
   6초로 조회했다. `/exchange/status`, `/series/KXCPI`, `/events`, `/markets`,
   `/historical/cutoff`, `/historical/markets` 모두 프록시 경유 ReadTimeout,
   직접 연결 ConnectError였다.
2. 개선된 `python scripts/probe_cpi_coverage.py --max-pages 1`을 실행했다.
   `/exchange/status` ReadTimeout, `/series/KXCPI`, `/historical/cutoff`,
   `/markets`, `/historical/markets`는 HTTP 403이었다. 두 시장 목록이 모두
   차단되어 `KXCPI-26AUG`의 사전 1분 캔들은 `access_error`로 생략됐다.
3. 공개 Kalshi 페이지에서 `KXCPI-26AUG`의 여러 CPI 임계값 계약을 확인했다.
   BLS는 해당 8월분의 실제 발표 일정을 2026-09-11 08:30 ET로 기록한다.
   이는 과거 가격 캔들 조회 성공과 같지 않다.

HTTP 403 응답이 네트워크 중개 장치인지 Kalshi 서버인지 식별하지 못했다.
API 키 부재도 원인이라고 단정할 수 없다. 공개 시장 데이터 공식 문서는 인증 없는
GET 경로를 설명하지만 현재 작업 환경의 네트워크 접근까지 보장하지 않는다.
우회 요청이나 인증정보 수집을 시도하지 않았다.

## 검증 결과와 한계

- `make PYTHON=.venv/bin/python quality`: Ruff 통과, Pyright 오류·경고 0개.
- `make PYTHON=.venv/bin/python test`: 72개 통과.
- 코드 점검기는 원본 확률을 저장하거나 가짜 시장 표본을 생성하지 않는다.
- MockTransport 검증은 **점검 절차의 동작**을 확인하며 실데이터 API 성공을 증명하지 않는다.
- `KXCPI-26AUG`의 1분 시계열과 ETF 세 종목의 장전 가격은 이번에 확보되지 않았다.

## 사용자 점검표

- [ ] 접근 가능한 PC 또는 합법적 데이터 환경에서
      `python scripts/probe_cpi_coverage.py --max-pages 1` 실행 결과를 확인했다.
- [ ] 임계값 계약의 정의와 발표 직전 신선한 양방향 호가·거래량이 있는 날짜를 집계했다.
- [ ] CPI 원본 최초 발표치와 ETF 가격의 공통 발표를 20 학습·10 시험 이상 확보했다.
- [ ] 데이터 보관·제품 시연의 이용 조건을 원천 제공자별로 확인했다.

원인에 따라 후속 작업은 [Kalshi CPI 접근·방법론 검토](../kalshi-cpi-access-methods.md)의
표대로 고른다. 이번 단계에서는 Kalshi 이용 불가 또는 예측력 확보를 어느 쪽도
확정하지 않는다.

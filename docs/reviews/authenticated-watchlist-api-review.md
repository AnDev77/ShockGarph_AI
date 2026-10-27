# 인증된 관심 자산과 공식 사건 조회 API 리뷰

작성일: 2026-10-27. 첫 사용자 동선인 관심 종목 선택과 그 종목의 공식 발표 목록 조회를 서버·DB 경계까지 구현했다. doChallenge의 기존 모임 채팅 인증 PR은 별도 저장소에 있으며 금융 사건 대화방과 합쳐졌다고 주장하지 않는다.

## 코드와 실제 완료 범위

- `apps/api/shockgraph_api/app.py`: Bearer JWT 서명·만료·발행 시각·숫자 회원 ID를 검증한다. `/v1/me/watchlist`에 QQQ·SPY를 추가·조회·삭제하고 `/v1/me/events`에서 서버 현재 시각 기준 사건 카드를 반환한다. 회원 ID를 요청값으로 받지 않는다.
- `apps/api/shockgraph_api/watchlist.py`: PostgreSQL의 회원별 종목 저장과 공식 사건·종목 관계 조회. SQL의 회원 ID는 값 파라미터로 결합하며 타인 목록 제거·조회 경로를 만들지 않는다.
- `infra/postgres/migrations/0003_watchlist_events.sql`: 관심 종목, 공식 발표 카드, 명시적인 발표·종목 관계를 별도로 둔다. 기존 Kalshi 사건의 의미를 바꾸지 않는다.
- `packages/domain/shockgraph_domain/event_feed.py`: 발표 자료가 실제 이용 가능한 시각 전에는 결과 링크가 응답에 들어가지 않는 기존 도메인 규칙을 재사용한다.
- `docs/api/watchlist-event-v1.md`: 요청 계약, 환경 설정, 출시 전 조건. `scripts/check_wheel_contents.py`에 API 패키지 3개를 추가했다.

## 시험 대상과 결과

합성 JWT·가짜 저장소 API 시험에서는 무인증, 틀린 서명, 만료, 잘못된 회원 ID, 지원하지 않는 종목을 거부하는지 확인했다. 두 회원을 분리해 타인 삭제가 첫 회원 목록을 바꾸지 않는지와, 관심 종목이 다른 회원에게 사건 카드가 나타나지 않는지 확인했다. 발표 원문의 이용 시각이 미래인 합성 카드에서 URL과 발표 완료 시각이 숨겨지는 것도 확인했다. SQL 경계의 가짜 커서 시험에서는 추가·조회·삭제와 사건 JOIN이 회원 ID를 파라미터로 묶는지 검사했다. 스키마 계약 시험은 회원·종목 키와 UTC 시각 타입을 확인한다.

로컬 `make test` 전체 193개 통과(신규 계약·API·SQL 경계 6개 추가). `make quality`에서 Ruff 오류 0건, Pyright 오류·경고 0건. wheel 빌드와 필수 소스 11개 포함 검사 성공. [초안 PR 원격 품질 게이트](https://github.com/AnDev77/ShockGarph_AI/actions/runs/40463661825)의 빌드·산출물 검사·정적 검사·전체 시험도 성공했다. 시험 과정에 HTTP 422 상수 이름의 사용 중단 경고와 긴 시험 줄, FastAPI 의존성 기본 인자에 대한 Ruff 오류가 있었고 상수·인자 선언·줄바꿈을 고쳐 재검사했다. 최신 시험에는 Starlette `TestClient`의 `httpx` 사용 중단 경고 1건이 남았다. 새로운 FastAPI·psycopg·PyJWT·uvicorn 의존성은 조회 API, PostgreSQL 저장, 기존 doChallenge JWT 형식의 검증, ASGI 실행에 각각 필요하다.

## 독립 평가와 한계

이 코드는 사용자별 접근 경계를 시험 가능한 수준으로 만들었다. 실제 PostgreSQL 서버와 마이그레이션 적용, 실토큰으로 두 서비스 연동, 회원 등록·탈퇴 동기화, 진짜 FOMC 공식 원문 수집은 아직 확인하지 않았다. API의 빈 사건 목록은 실제 분석 완료나 사용자 가치의 증거가 아니다. JWT에는 issuer·audience가 없어 서비스 사이 토큰 범위를 충분히 한정하지 못한다. 두 서비스 비밀값 공유 대신 명시적 발급자·대상 또는 별도 검증 키 계약으로 전환하고 종목 수 제한·오남용 대응을 출시 전에 구현해야 한다. 프로세스 생존 응답은 DB 준비 상태를 증명하지 않는다.

증권사 리서치 팀 관점에서 사건·종목 연결, 관측 가능 시각, 사용자별 접근은 필요한 기반이다. QQQ/SPY 수익률 비교, 장중 발표 반응, 역사적 사건 분포 및 불확실성은 아직 코드와 실자료가 없으므로 금융 분석 성과는 없다. 모델 A/B의 실제 미래 결과 판정은 계속 HOLD다. 다음에는 공식 FOMC 발표 자료와 QQQ 원본의 출처·시각·권리를 확인한 뒤, 같은 구간 비교 계산을 구현해야 한다.

## 최신 main·예약 수집·연구 판정

2026-10-27 확인 시 main은 2026-10-26 PR #7 병합 커밋 `a993373`이고, 초안 PR #8~#11은 열려 있다. 이 기능은 PR #11에 쌓았으며 다른 초안의 PostgreSQL 공식 점수 기능이나 수집 시간 수정과 합치거나 병합하지 않았다. main의 `private-forward-capture.yml` 예약은 뉴욕 시간 평일 07:10으로 등록돼 있다. [마지막 확인 가능한 10월 26일 예약 실행](https://github.com/AnDev77/ShockGarph_AI/actions/runs/40367432971)은 전체 성공이지만 사전 검사 뒤 가격 원본 보관 단계는 생략됐다. 비공개 원격 감사와 점수 저장 단계는 성공 상태였으나 신규 거래일 가격 보관 또는 새로운 성과를 뜻하지 않는다. 10월 27일 오후 확인 시 같은 워크플로의 그날 예약 실행은 목록에 없었다. 다음 실행의 실제 수집 여부는 별도로 확인해야 한다.

[연준 2026-09 개정 연구](https://www.federalreserve.gov/econres/feds/linear-and-nonlinear-econometric-models-against-machine-learning-models.htm)는 S&P 500·40개 주식의 고빈도 실현 변동성을 HAR·ARFIMA·상태전환 HAR·XGBoost·신경망으로 비교한다. 5일·월간 기간별 우열이 다르고 ML이 항상 기존 계량 모형을 앞서지 않았다. 우리의 미래 목표는 TLT 5·20거래일의 **일별 가격 기반 변동성**이며 논문의 고빈도 실현 변동성과 같지 않다. B 후보를 추가하려면 가격 기반 A와 동일한 시작일·정답 정의, 발표 당시 이용 가능 입력, 서로 겹치는 정답의 의존성 처리 및 새 독립 시험이 먼저 필요하다. 현재 사건 카드 API는 예측 모델 평가가 아니다.

[연준 2026 FOMC 주가 연구](https://www.federalreserve.gov/econres/feds/the-effect-of-the-federal-reserve-on-the-stock-market-magnitudes-channels-and-shocks.htm)는 좁은 발표 시각 창의 정책 놀라움과 발표 전후 정보 경로를 구분한다. 현재 QQQ 장중 가격·발표 전 기대치가 없으므로 그 연구를 근거로 QQQ/SPY 차이를 FOMC의 인과적 충격이라고 표시할 수 없다. [BlackRock의 자본시장 가정](https://www.blackrock.com/institutions/en-global/institutional-insights/thought-leadership/capital-market-assumptions)은 여러 경로와 자산 간 위험·상관을 다루는 장기 기관 시나리오 자료다. 이는 시나리오 표현과 불확실성 표시의 참고이지 이번 사건의 일별 수익률 정답이나 개인별 매매 근거가 아니다. 소프트웨어 품질 통과, 미래 예측 우위 및 한국 사용자 재방문 수요는 서로 별개이며 뒤의 두 가지는 미검증이다.

## 사용자 점검 기준

첫 회원의 QQQ 관심 목록을 두 번째 회원의 JWT로 삭제하거나 읽을 수 없어야 한다. 공식 발표를 보관하기 전에는 예정 카드만 노출되어야 한다. 다른 종목이나 미지원 종목을 임의로 가격 분석이 가능한 것처럼 표시해서는 안 된다.

# Review: CAMT 공시 수집과 검토된 브리핑 조회

## 현재 작업 대기열과 브랜치 정리

2026-11-17 KST, [브랜치 정리 기록](docs/reviews/branch-cleanup-2026-11-17.md)에 원래 브랜치·head SHA·보관 경로, PR별 제외 이유, 바뀐 문서 구조와 검증 결과를 기록했다. 원격 23개 분기는 main·현재 기능·보관 8개로 정리했고 열린 PR은 #18 하나다. 최신 후속 순서는 [일일 계획](docs/daily-work-plan.md)을 따른다. 실행 코드나 신규 런타임 기능은 바꾸지 않았으며, 이번 환경에서 기존 #18의 194개 시험·정적 검사·wheel 소스 12개 검사를 직접 통과했다. main 병합과 운영 배포는 수행하지 않았다.

## 시작과 목적

2026-11-15 KST. Python main `a993373`에서 새 브랜치를 만들었다. [웹 계획 #8](https://github.com/AnDev77/shockgraph-web/pull/8)과 [웹 구현 #9](https://github.com/AnDev77/shockgraph-web/pull/9)의 브리핑 JSON 계약을 기준으로 작업했다. 기존 포트폴리오·가격 수집 초안을 합치지 않고 자료 수집부터 조회까지 구현했다.

## 바뀐 구조와 확인할 코드

| 파일 | 역할 |
|---|---|
| [filings.py](packages/briefing/shockgraph_briefing/filings.py) | SEC 제출 목록에서 CIK·티커·수리 시각을 확인하고 CAMT 6-K/20-F 원문을 내려받는다. 고정 호스트·검증된 경로, 리다이렉트 금지, 응답 크기·형식 제한. 원문 SHA-256과 수집·수리 시각, 정제한 문단을 남긴다. |
| [pipeline.py](packages/briefing/shockgraph_briefing/pipeline.py) | 실적·전망·위험 키워드로 문단 최대 8개를 골라 구조화 요약 초안을 만든다. 검증된 수치 전용 계약이 생기기 전까지 모델 숫자 표기를 차단한다. 문단 ID와 원문 해시를 검사하고 사람이 대조한 초안의 해시로만 공개 결과를 만든다. 회사 자료 한 건이므로 방향 판단은 보류한다. |
| [명령](packages/briefing/shockgraph_briefing/__main__.py) | 수집·생성·검토 완료의 세 명령을 분리. 현재 시점에 7일 밖인 문서는 생성과 신규 공개 모두 거부한다. |
| [FastAPI](apps/briefing_api/shockgraph_briefing_api/app.py) | 내부 토큰을 요구하는 읽기 전용 조회. HTTP 요청 중 원문·LLM을 호출하지 않는다. 미검토·자료 부족·수집 실패를 구분하며, 이미 검토된 요약은 자료 날짜에 따라 이전 결과로 표시하고 30일 이후에는 더 이상 반환하지 않는다. |
| [시험](tests/unit/test_camt_briefing.py) | 미래 문서 배제, 잘못된 발행자·문서 경로·리다이렉트 거부, 초안 미노출, 인용 연결, 오래된 자료와 수집 실패 구분, 모델 불완전 응답 거부. |

흐름: **SEC 목록 → 원문 수집 → 관련 문단 선택 → 구조화 요약 초안 → 사람 검토 → FastAPI 조회**.
JSON 파일은 파일 교체 방식으로 저장하며 이번에는 로컬 파일만 사용한다. 유료 모델 호출을 켜거나 운영 네트워크를 구성하지 않았다. 웹 공개 요청은 별도 Java 프록시를 통하며 내부 토큰은 브라우저로 보낼 수 없다.

## 실행과 검토

```sh
python -m pip install -e '.[dev,viz,briefing]'
# SHOCKGRAPH_SEC_USER_AGENT에 수집 앱 이름과 운영자 연락처를 설정한다.
python -m shockgraph_briefing collect
# 사용 조건 확인 후, 서버 비밀 저장소에서 OPENAI_API_KEY와 모델명을 주입한다.
python -m shockgraph_briefing draft --allow-source-transfer
# 생성된 draft-camt.json의 각 주장과 원문을 사람이 대조한다.
python -m shockgraph_briefing publish --reviewed-sha256 <검토한-초안의-SHA256>
# BRIEFING_INTERNAL_TOKEN은 백엔드에서만 설정한다.
python -m uvicorn shockgraph_briefing_api.app:create_app --factory --host 127.0.0.1 --port 8785
```

모델 식별자는 `SHOCKGRAPH_BRIEFING_MODEL` 환경 변수로 설정한다. 허용된 출처에 대해서만 외부 모델 전송을 승인한다. 인용 ID 검사는 문장의 의미나 수치가 원문과 일치함을 자동 보증하지 않는다. 공시 본문과 실행 아티팩트는 Git에 넣지 않는다.

## 중간·완료 검증

- [SEC 공시](https://www.sec.gov/Archives/edgar/data/1109138/000117891326005000/zk2636329.htm)의 원문을 CLI로 실제 수집했다. CAMT 6-K `0001178913-26-005000`의 SEC 수리 시각은 **2026-11-04 21:03:59 KST**이고, 11/15 현재 7일 밖이다. 정제 문단 130개 중 실적과 회사 전망 관련 문단이 모두 검색되는 것을 확인했다. 초기에 단수 키워드만으로 일부 매출 문장을 놓쳐 복수형과 성장률 표현을 추가했다.
- 실제 로컬 HTTP에 웹 #9의 Zod 파서를 붙여 현재 `insufficient_sources`를 확인했다. 동일 공시를 과거 날짜로 재현한 별도 임시 데이터에서 사람이 작성·대조한 요약은 `ready/stale/withheld`와 원문 인용으로 검증했다. 과거 날짜를 재현한 시험이며 그날 수집했거나 LLM이 요약한 기록으로 계산하지 않는다.
- 로컬 Ruff·Pyright, 전체 pytest 188건, wheel 빌드와 필수 포함 파일 11개 검사 통과. 설치한 Starlette의 TestClient가 httpx 사용 중단 예정 경고를 반환했으며 실패는 없었다.
- 실제 LLM 생성은 API 키·모델 설정 부재와 7일 범위 내 공시 부재로 미실행이다. 구조화 모델 응답과 오류는 합성 응답으로 검증했다. 공개 배포, 회원 데이터 결합, 임베딩·LangGraph, MySQL 발행 저장, 독립 출처 검증 및 방향 판단은 이 단계의 완료 범위가 아니다.


## RAG 초안의 Kafka 작업 전달 실험

### 결정과 추가 기능

2026-11-17 KST. 예측 워커보다 먼저 CAMT 공시 RAG·LLM 요약에 Kafka를 연결한다. 기존 수집·검색·요약·사람 검토·읽기 API의 책임을 유지한다. 화면 조회나 Java 회원·채팅을 Kafka 소비자로 만들지 않는다. Kafka 사용은 격리 시험이며 실제 운영 연결 완료가 아니다.

| 바뀐 파일 | 추가·변경된 기능 | 그렇게 만든 이유 |
|---|---|---|
| packages/briefing/shockgraph_briefing/kafka_jobs.py | enqueue가 CAMT 수집 결과의 해시별 스냅샷과 작업 의도를 기록한다. relay가 Kafka 작업 이벤트를 발행하고 성공 확인 후 전송 표식을 남긴다. work-once가 한 건을 읽어 초안을 만들고 저장 뒤 offset을 확정한다. | 수집·LLM·공개를 서로 분리한다. 브로커 메시지에는 ID·원본 해시·모델·요청 시각만 포함하고 원문·키·모델 출력을 넣지 않는다. Kafka가 느리거나 중복 전달해도 HTTP 조회에서 LLM을 실행하지 않는다. |
| tests/unit/test_kafka_briefing_jobs.py | 합성 공시와 가짜 생산자·소비자로 발행 실패·중복·출처 불일치·기간 초과·이전 작업의 스냅샷 보존·offset 순서를 확인한다. | 실제 SEC·유료 LLM·비밀값 없이 실패 경계를 재현한다. 실브로커 통합 시험을 대체한다고 주장하지 않는다. |
| pyproject.toml, scripts/check_wheel_contents.py | Kafka Python 클라이언트는 선택 설치로 분리하고 wheel에 새 모듈이 들어가는지 검사한다. | Kafka를 사용하지 않는 기존 분석·API 설치가 브로커 의존성을 강제로 받지 않도록 한다. |
| AGENTS.md, docs/current-product-direction.md, Review.md | Kafka 첫 적용 경계와 이후 리뷰 작성 규칙을 갱신한다. | 이전의 Kafka 금지보다 최신 사용자 결정을 우선하고, 향후 기능별로 변경 이유와 한계를 찾을 수 있게 한다. |

### 순서와 확인할 코드

1. 기존 python -m shockgraph_briefing collect로 수집한 뒤 python -m shockgraph_briefing.kafka_jobs enqueue를 실행한다. 수집 파일과 SHA-256별 스냅샷은 공유된 작업 디렉터리에 남고 작은 작업 의도를 기록한다.
2. 별도 relay 프로세스가 작업 ID를 key로 shockgraph.briefing.draft.v1 토픽에 보낸다. 브로커 승인 전에 전송 완료를 기록하지 않는다. 확인 응답 유실 때 재발행될 수 있다.
3. 별도 work-once --allow-source-transfer 프로세스가 해당 해시 스냅샷과 7일 적격성, 설정된 모델을 재확인하고 기존 retrieve와 openai_summary로 초안을 만든다. 초안 파일이 저장된 다음에만 Kafka offset을 확정한다. 같은 작업의 중복 메시지는 이미 저장한 초안을 재사용한다.
4. 초안은 여전히 비공개다. 사람이 내용·인용을 대조한 뒤 기존 publish --reviewed-sha256 명령을 실행해야 공개 조회 API가 결과를 보여준다.

격리 시험 순서: python -m pip install -e '.[dev,viz,briefing,kafka]' → collect → SHOCKGRAPH_BRIEFING_MODEL을 설정한 enqueue → SHOCKGRAPH_KAFKA_BOOTSTRAP을 추가한 relay → OPENAI_API_KEY를 비밀 설정에서 주입한 work-once --allow-source-transfer. 이는 운영 절차가 아니다. 원문을 외부 LLM에 전송할 권리와 운영자 동의가 확인되어야 마지막 단계를 실행한다. 키·원문을 채팅·공개 로그·커밋에 입력하지 않는다.

### 전달 보장과 한계

- 파일 기록은 원자적 교체를 이용하지만 수집 파일·스냅샷·작업 의도·Kafka 발행이 하나의 DB 트랜잭션은 아니다. 중간 중단 시 재실행·대조가 필요한 파일 기반 실험이다. 브로커 전송 확인이 유실되면 중복 전송될 수 있으므로 작업 ID와 해시별 초안으로 중복을 줄인다. 중복 LLM 호출을 모든 경쟁 조건에서 막는다고 주장하지 않는다.
- 현재 코드는 동일 공유 디렉터리를 보는 생산자와 소비자만 지원한다. 여러 EC2나 독립 워커로 확장하려면 불변 객체 저장소, DB 트랜잭션 아웃박스, 공유 작업·결과 DB와 접근 권한이 필요하다. 실브로커 연결, 인증/TLS, 토픽 생성, 죽은 메시지 처리, 소비 지연 계측 및 워커 운영은 아직 검증 대상이다.
- 과거 작업은 자기 해시의 스냅샷과 초안 파일을 사용하며 최신 초안 포인터를 덮어쓰지 않는다. 현재 공개 API는 사람이 검토한 결과 파일만 읽고, 예측 성능 판정은 계속 HOLD다.

### 시작·중간·완료 검증 기록

- 시작: Python main과 열린 PR을 조회했다. RAG 구현은 초안 PR #18에 있으며 main에는 아직 없다. 기존 CLI는 동기 LLM 초안 명령, 조회 API는 검토된 결과만 읽는 상태였다.
- 중간: 원문 대신 작업 참조를 보내고, 브로커 확인 후 표식 기록·초안 저장 후 offset 확정·중복 작업 재사용을 설계했다. 스냅샷 없이 최신 수집 파일만 읽으면 다음 공시가 이전 작업을 밀어낼 수 있어 SHA-256별 불변 파일을 추가했다.
- 완료 판정은 새 커밋의 wheel, Ruff/Pyright, 전체 시험, 원격 PR 게이트에서 따로 확인한다. 이 환경에서는 로컬 Python 실행기가 없어 코드 실행 결과를 검증했다고 적지 않는다. 실제 Kafka/LLM/SEC 호출과 운영 배포는 미실행이다.


### 원격 품질 게이트 결과

2026-11-17 KST, PR #18 새 커밋 4e5fd34의 빌드와 품질 게이트에서 wheel 빌드와 필수 소스 파일 12개 포함 검사가 성공했다. Ruff는 위반 0건, Pyright는 오류·경고·정보 0건이었다. 전체 pytest는 194건 성공·경고 1건으로 종료됐으며, 새 작업 전달 시험 6건은 합성 공시와 가짜 Kafka 생산자·소비자로 실행됐다. 이는 파일 의도·메시지 계약·중복·오류 때 offset 미확정 경로의 자동 시험 결과이며 실제 브로커 기동, 소비자 재균형, 네트워크 단절 뒤 재처리, 실제 LLM 호출이나 운영 전환을 증명하지 않는다. 실행 환경에 로컬 Python 실행기가 없어 로컬 make quality/test는 별도로 수행하지 못했다. 문서 갱신 뒤 최종 커밋의 CI 상태는 다시 확인한다.

## 사전 예측 표본이 늘지 않는 이유의 감사 (2026-11-18)

- 변경 구조: 원본 해시·시각 재검사 뒤 예측 기록과 원본 전용 기록을 나누고, 원본 전용 기록을 시간 조건 실패·거래일 달력 부족으로 집계한다.
- 기능과 이유: 작업 성공을 새 예측 성공으로 오해하지 않고 고유 거래일 수와 보류 원인을 따로 확인한다. scripts/audit_private_capture.py와 tests/integration/test_private_forward_archive.py를 함께 읽는다.
- 상세 시작·중간·완료 근거와 한계는 [기능 리뷰](docs/reviews/forecast-capture-coverage-diagnostics.md)에 기록한다. 이번 변경은 읽기 전용 진단이며 모델·일정·원본·점수를 바꾸지 않는다.

## 실행 성공과 사전 예측 마감의 분리 (2026-11-19)

- scripts/audit_capture_timing.py와 tests/unit/test_capture_timing_audit.py를 기존 연구 감사 #20에 추가했다. 원본 마지막 거래일과 공개 실행 시각으로 개장 전 시간 여유를 검증하고, 원본 보관 완료 여부는 미확인으로 남긴다.
- 공개 실행이 늦은 것과 워커 시작이 늦은 것을 구분하기 위한 구조다. 원문·가격·비밀값·점수 없이 원인을 좁히며 원본을 과거 시각으로 소급하거나 모델 성능 판정을 바꾸지 않는다.
- 주말·공휴일·서머타임·마감 경계·잘못된 시각을 시험한다. 시작·중간·완료와 실제 메타데이터 가정, 오류·미검증 범위는 [감사 리뷰](docs/reviews/forecast-capture-coverage-diagnostics.md)에 기록했다. 예약·Java·웹·운영 배포는 변경하지 않았다.

## 늦은 수집으로 사전 예측이 쌓이지 않는 병목 수정 (2026-11-20)

- 바뀐 구조: `capture_window.py`가 실제 폐장·수집 지연 조건으로 거래일을 고르고, Alpaca 수집기는 그날 장 종료 후에도 지연 SIP 범위 안에서 요청한다. `private-forward-capture.yml`은 뉴욕 저녁 20:23에 먼저 시도하고 00:23·06:23에 재시도한다.
- 선택 이유: 최근 실행은 마감 뒤 생성되어 원본만 저장했으며, 기존 당일 수집 금지와 아침 단일 예약 때문에 선제 수집이 불가능했다. 타임스탬프를 앞당기거나 이미 지난 정답을 예측했다고 기록하지 않고 수집 기회를 전날 저녁으로 옮긴다.
- 추가 기능: `audit_private_capture.py --latest --expected-origin`으로 실제 원격 감사 후 해당 거래일 TLT/SPY 예측 둘이 있어야 성공한다. 원본 보관 성공·이전 예측만으로 성공 표시하지 않는다. 정답 정의와 모델은 그대로다.
- 실행 흐름·작업량·코드 경로·시험·오류·남은 한계·운영 적용 조건은 [사전 예측 저장 병목 복구](docs/reviews/evening-forward-capture-recovery.md)에 기록한다. 실제 예약 복구와 모델 성능 HOLD 해제는 별도 확인이다.

## 원본 거래일과 예측 정답 기간의 대조 (2026-11-20)

- `scripts/archive_forward_capture.py`의 원격 감사가 검증한 CSV 마지막 거래일을 예측 기준일과 대조한다. 5·20거래일의 시작·끝·폐장 시각과 기간 중복도 검사한다.
- 해시 일치만으로 잘못된 날짜가 통과할 수 있어 추가한 검증이다. 기존 원격 감사·재고·공식 채점 흐름을 공유하고 외부 요청은 늘리지 않는다.
- 변경 구조·선택 이유·5개 재현 시험·시작/중간/완료·세 저장소 상태·운영 한계는 [원본 달력 검증 리뷰](docs/reviews/forecast-source-calendar-validation.md)에 기록한다. 실제 수집 성공과 모델 성능은 이 변경의 완료 주장에 포함하지 않는다.

## 사전 예측 수치의 유효성 검사 (2026-11-23)

- `scripts/archive_forward_capture.py`에서 저장된 네 변동성 값의 숫자 형식·유한성·음수 여부를 검사한다. 해시와 날짜가 맞더라도 NaN·무한대·음수·bool·문자열·null이면 감사를 실패시킨다.
- 잘못된 값이 정상 예측 재고나 채점에 들어가지 않도록 공통 감사 함수에 배치했다. 정상 0은 허용하고 모델 계산·데이터 삭제·원격 호출 추가는 없다.
- `tests/integration/test_private_forward_archive.py`의 합성 오류 주입 28건과 [기능 리뷰](docs/reviews/finite-risk-archive-validation.md)에서 구조·이유·작업량·시작/중간/완료·운영 한계를 확인한다. 운영 예약 적용과 모델 성능 판정은 별도다.

## 거래일 달력 종료 시 원본과 정답 보존 (2026-11-24)

- `market_calendar.py`의 `reviewed_future_sessions`로 수집·예측·감사의 미래 거래일 조회를 통일했다. 마지막 검증 날짜에서는 빈 일정을 반환하고 미검증 연도를 임의 연장하지 않는다.
- `archive_forward_capture.py`가 12/31 원본 쓰기 후 역전된 날짜 범위로 중단되던 문제를 수정했다. 새 예측이 불가능해도 원본 전용 index를 남겨 이전 예측의 정답 채점에 사용할 수 있게 한다.
- `check_capture_due.py`와 예약 워크플로는 달력 부족과 마지막 지원 기준일을 알리되 가격 수집을 막지 않는다. 기존 새 예측 필수 확인은 그대로 유지한다.
- 변경 이유·실행 흐름·12개 파일 작업량·실패 재현·전체 269개 시험·wheel 필수 소스 14개·운영 한계는 [기능 리뷰](docs/reviews/calendar-boundary-snapshot-review.md)에 기록했다. 공식 Nasdaq 2027 일정 미확인, #20 미병합, 실전 성능 HOLD는 남아 있다.

## 연구 PR 통합 준비 검증 (2026-11-25)

- #19와 #20은 개별적으로 main에 병합 가능하지만 서로 합치면 Review.md에서 충돌함을 재현했다. 격리된 로컬 후보에서 역할 변경과 연구 복구의 양쪽 추가 기록을 보존했다.
- 실행 코드는 바꾸지 않았다. 신규 기능을 쌓기보다 진행 중 수집 복구의 통합 위험을 확인했으며 전체 269개 시험, 정적 검사, wheel 필수 소스 14개 검사가 통과했다.
- [통합 준비 리뷰](docs/reviews/pr-integration-readiness-review.md)에 정확한 head·후보 tree·권장 순서·작업량·오류·운영 한계를 기록했다. 원격 병합/배포는 하지 않았고 실제 수집에서 새 예측 거래일 증가도 없었다.

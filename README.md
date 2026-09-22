# ShockGraph AI

ShockGraph AI는 거시 이벤트를 기반으로 포트폴리오 위험을 연구하는 MVP다.
예측시장 확률을 보정하고, 자산 반응의 시차를 추정하며, 시나리오별 위험이 사용자의 포트폴리오에 어떻게 전달되는지 설명한다.
거래 실행과 개인화된 매수·매도 권유는 제공하지 않는다.

## 현재 구현 상태

1~6일차 작업에서 데이터 계약과 발표 단위 기준 모델 비교 파이프라인까지 구현했다.

- API, 웹, 수집기, 분석 패키지, 인프라의 저장소 구조
- Kalshi API 계약 검증용 고정 응답 자료
- 응답 정규화와 원본 해시 계산
- 이벤트 단위 분할과 시각 기반 미래 정보 누수 방지
- 읽기 전용 공개 API의 기술적 가용성 확인 스크립트
- 진행 가능·범위 축소·보류 판단 문서
- UTC를 강제하는 이벤트, 시장 관측, 호가창 데이터 계약
- 원본 추적 제약조건을 갖춘 PostgreSQL 수집 스키마
- 재시도 횟수 제한과 커서 페이지네이션을 갖춘 GET 전용 공개 수집기
- 내용 기반 불변 원본 저장
- S3 호환 객체 키·저장 프로토콜과 불변 로컬 어댑터
- 큐·저장소 인터페이스와 원본 정규화 작업의 멱등 키
- TimescaleDB용 자산 가격·특징량 스키마와 트랜잭션 아웃박스 스키마
- UTC에서 미국·한국 거래소 현지 날짜로의 변환과 기준시점 정렬
- 이벤트별 시간순 확률 보정 데이터 분할
- 시장확률을 그대로 사용하는 기준 모델과 Brier 점수·표본 수·불확실성 계산
- 모델 산출물·체크섬·버전·평가 지표 등록 계약

- 발표 전 확률·기대·가격의 시점 검증과 이벤트별 커버리지·제외 사유
- 과거 수익률 분포와 이벤트 확률 가중 분포의 순차 학습·평가
- 자산·포트폴리오 CRPS, 상승확률 Brier, 하방 분위수 손실, 발표 단위 대응 재표집
- 정규화 입력과 결과 체크섬을 포함한 재현 리포트 CLI 및 합성 실행 예제

실데이터로 검증된 예측 모델과 웹 화면은 아직 없다. 실제 데이터베이스 연결과 운영 검증도 후속 범위다.

현재 작업 결과는 [분석 개발 리뷰](docs/reviews/day-05-06-review.md),
재접속 후 상태는 [연동·재검증 기록](docs/reviews/analytics-sync-checkpoint.md), 목표 구조는
[아키텍처 문서](docs/architecture.md)에서 확인할 수 있다.

## 학습과 제품 설계

- [이벤트 분석 파이프라인 학습 가이드](docs/study-guide-analytics.md): 실행 방법, 시간 누수, 경험적 분포, CRPS, 지속 학습과의 연결
- [이번 CPI·ETF 커버리지 점검](docs/cpi-coverage-review.md): 접근 실패·키 미설정과 실데이터 연결 조건
- [데이터 파이프라인·확률 평가 학습 가이드](docs/study-guide-day-03-04.md): 6회 학습 순서, 코드 읽기, 실습, 금융 예제, 구현 한계
- [제품·Chakra UI 화면 설계](docs/product-ui-direction.md): 사용자 종목 선택, 이벤트 분석, 모바일 화면, 결과 표시 기준

설정 파일의 자산 목록은 분석 후보이며 학습 완료 목록이 아니다.
사용자는 지원되는 자산·이벤트·기간 조합에서 선택하게 된다. 예측 API와 Next.js·Chakra UI 화면은 구현 예정이다.

## 로컬 실행

Python 3.12가 필요하다. 아래는 Windows 기준 명령어다.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```

macOS와 Linux에서는 `.venv/bin/python`을 사용한다.

가상환경의 Python으로 합성 이벤트 분석을 실행할 수 있다.

```bash
python scripts/run_event_research.py --input data/fixtures/analytics/synthetic_cpi.json --min-train 4
```

결과는 `artifacts/event-research/`에 저장되며 합성 결과는 금융 성능 근거가 아니다.

## 저장소 구성

- `apps/api`: 2주차 구현 예정인 FastAPI 영역
- `apps/web`: 3주차 구현 예정인 Next.js 영역
- `apps/collector`: 읽기 전용 수집 영역
- `packages/domain`: 금융 데이터·포트폴리오 계약
- `packages/data_pipeline`: 원본 계약, 객체 저장, 멱등 정규화, 계보 추적, 거래시각 정렬, 누수 방지
- `packages/calibration`: 이벤트별 데이터셋과 시장확률 기준 모델·Brier 평가
- `packages/*`: 후속 이벤트 연구, 전이 분석, 위험 계산 영역
- `docs/data-feasibility.md`: 1일차 데이터 가용성 검토와 범위 결정
- `docs/data-source-gate-b.md`: 미국 자산·환율·국내 자산 공급원 검토
- `docs/architecture.md`: 원본 우선 수집과 데이터·모델·서빙 계층의 목표 구조
- `data/fixtures`: 원본 응답 형태를 따른 소규모 고정 테스트 자료
- `docs/reviews`: 요청별 변경 구조와 사용자 점검표

## 작업 규칙

문서는 한글로 작성하고, 커밋 제목에는 일차 대신 주요 변경 내용을 적는다.
상세 규칙은 [AGENTS.md](AGENTS.md)를 따른다.

공개 읽기 전용 엔드포인트나 데모 환경만 사용한다.
비밀키, 계정 데이터, 주문·거래 실행은 MVP 범위 밖이다.

# ShockGraph AI 아키텍처

상태: 일별 위험 분석으로 전환 중. 새 프로그램 구조는 목표 설계이고, 아래 이벤트 중심 구조는 기존 연구 아키텍처 이력이다.
개정일: 2026-10-19

## 새 프로그램 구조: 일별 ETF 위험

일별 ETF 위험이 주 경로다. 실선은 목표 프로그램의 기본 경로이고 점선은 조건이
충족된 뒤 연결할 경로다. 아래 그림은 **완료된 배포 구성이 아니다.** 실제 구현
여부는 그림 아래의 표와 [프로젝트 흐름도](project-flow.md)를 따른다.

```mermaid
flowchart TB
    S["권리 확인된 TLT 수정가격"] --> C["수집 작업"]
    O["브렌트·금리·VIX"] -.-> C

    subgraph DATA["원본 저장·정규화"]
        RAW[("S3 호환 불변 원본")]
        META[("PostgreSQL 수집 메타·아웃박스")]
        PUB["아웃박스 발행기"]
        MQ["RabbitMQ 메시지 큐"]
        N["멱등 정규화 작업"]
        PANEL[("PostgreSQL / TimescaleDB 일별 패널")]
    end
    C --> RAW
    C -->|원본 저장 성공 후| META
    META -->|초기: 직접 실행| N
    META -.-> PUB
    PUB -.-> MQ
    MQ -.-> N
    N --> PANEL

    subgraph MODEL["오프라인 모델·검증"]
        F["예측 시점에 이용 가능한 특징량"]
        L["5·20거래일 뒤 실제 변동성·사후 확정"]
        B["최근 변동성·EWMA 기준 모델"]
        M["브렌트·금리·VIX 후보 모델"]
        E["같은 기간 시간순 평가·승격 게이트"]
        ART[("S3 호환 모델 산출물")]
        REG[("PostgreSQL 모델 메타·평가 지표")]
        SNAP[("PostgreSQL 승인된 위험 스냅샷")]
    end
    PANEL --> F
    PANEL --> L
    F --> B --> E
    F -.-> M -.-> E
    L --> E
    E --> ART
    E --> REG
    E -->|검증 통과만| SNAP

    subgraph SERVE["조회 서비스"]
        WEB["Next.js 웹"]
        APP["후속 모바일 앱"]
        API["FastAPI 읽기 API"]
        CACHE[("Redis 검증 결과 캐시")]
    end
    WEB --> API
    APP -.-> API
    API --> SNAP
    API -.-> CACHE
```

| 실행 영역 | 저장소 위치와 현재 상태 | 다음 연결 |
|---|---|---|
| 수집·정규화 | `apps/collector`, `packages/data_pipeline`: 기존 Kalshi 수집·원본 저장 및 정규화 계약 | 허가된 TLT 공급원, 실제 세션 달력, `available_at`, 일별 패널 영속화 |
| 메시지 큐 | `infra/postgres/migrations/0002_day03_04.sql`: 아웃박스 **스키마만** 존재. RabbitMQ·발행기·소비자는 미구현 | 객체 저장 완료 뒤 메타·아웃박스의 단일 DB 트랜잭션, 멱등 소비 및 재시도 검증 뒤 도입 |
| 모델·평가 | `packages/risk_engine`: 합성 가격의 5·20일 최근 변동성/EWMA 기준선 및 시점 검사 구현 | 실자료 표본 외 검증, 시장 변수 증분 비교, 일별 모델 등록·스냅샷 스키마 |
| API·화면 | `apps/api`, `apps/web`: 자리만 있음 | 승인된 스냅샷을 읽는 FastAPI와 Next.js 화면 연결 |
| 캐시 | Redis 미연결 | 조회 지연 측정 뒤 검증된 API 응답에만 적용 |

초기에는 수집·정규화·평가를 독립 실행 작업으로 연결한다. **메시지 큐는 학습
데이터나 API 응답의 저장소가 아니다.** RabbitMQ가 필요해지면 객체 저장 성공 후
PostgreSQL 수집 메타와 아웃박스 행을 한 트랜잭션으로 기록하고, 발행기는 원본
식별자와 변환 버전만 전달한다. 정규화 소비자는 중복 전달을 처리하며 DB 반영이
확인된 뒤 메시지를 확인 처리한다. 예약 실행이나 Prefect는 작업을 조율할 수
있지만 데이터 본문을 전달하지 않는다.

기준 모델과 후보 모델은 `prediction_at` 이전에 이용 가능했던 입력만 사용한다.
그림의 사후 확정 값은 예측 당시에는 존재하지 않는다. 뒤따르는 5·20거래일의
실제 가격이 모두 이용 가능해진 뒤 계산해, 과거에 만든 예측의 평가와 이후
학습에만 쓴다. 모델 산출물은 S3 호환
저장소에, 버전·평가 지표·승인된 결과 스냅샷은 PostgreSQL에 기록한다. API는
스냅샷만 읽고 요청 중에 학습하지 않는다. 검증된 결과가 없으면 수치를 만들지
않고 상태와 이유를 반환한다. 원본 및 모델 산출물 상자는 동일한 S3 호환 저장소의
서로 다른 논리 영역을 나타낸다.

기존 Kalshi 수집·보정은 독립 이벤트 연구 모듈이며 일별 위험 API의 필수 경로가
아니다. 후속 주주 인증 채팅은 별도 [권한 및 운영 설계](shareholder-community-roadmap.md)를
통과한 뒤 API·웹에 연결한다. Kafka·Kubernetes는 초기 범위 밖이다.

아래 섹션은 과거 이벤트 연구용 설계로 남긴다. 신규 구현의 우선순위와 데이터
단위는 [일별 위험 방법론](daily-risk-methodology.md), [프로젝트 흐름도](project-flow.md),
최상위 [프로젝트 명세](../shockgraph-ai-project-spec.md)를 따른다.

## 기존 이벤트 연구 목적

데이터 수집, 저장, 모델 학습, API 제공 영역을 정의한다.
현재 구현 상태는 [데이터·확률 평가 개발 리뷰](reviews/day-03-04-review.md),
제품 범위는 [프로젝트 기획서](../shockgraph-ai-project-spec.md)를 기준으로 판단한다.

## 아키텍처 원칙

1. 원본을 먼저 저장하고 이후 단계를 원본에서 재현할 수 있어야 한다.
2. 메시지가 중복 전달될 수 있으므로 모든 소비자는 멱등이어야 한다.
3. 작업 조율기는 작업을 제어하지만 데이터 본문의 전달 경로는 아니다.
4. Redis와 특징량 저장소는 원본 데이터의 기준 저장소가 아니다.
5. 모델 바이너리와 대용량 스냅샷은 객체 저장소에, 관계형 메타데이터는 PostgreSQL에 둔다.
6. 시계열과 관계형 데이터는 PostgreSQL과 TimescaleDB로 시작한다.
7. 웹은 FastAPI만 호출하며 DB와 캐시에 직접 연결하지 않는다.
8. MVP 배포는 로컬·Docker에서 검증하고, 상용 전환은 관리형 컨테이너에서 시작한다.

## 기존 이벤트 연구 목표 구조

```mermaid
flowchart TB
    subgraph SOURCE["외부 데이터"]
        K["Kalshi"]
        M["시장 가격"]
        E["경제지표 발표"]
    end
    subgraph INGEST["수집 계층"]
        C["수집기"]
        O[("S3 / MinIO")]
        P[("PostgreSQL 메타데이터")]
        X["아웃박스 발행기"]
        Q["RabbitMQ"]
        W["정규화 작업 프로세스"]
    end
    subgraph DATA["데이터 계층"]
        T[("PostgreSQL + TimescaleDB")]
        F["SQL 특징량 스냅샷"]
    end
    subgraph CONTROL["작업 제어 계층"]
        PF["Prefect"]
    end
    subgraph ANALYTICS["분석 계층"]
        CAL["확률 보정"]
        ES["이벤트 연구"]
        TR["전이 분석"]
        RK["위험 계산"]
        MR[("모델 등록부")]
        PR[("예측 결과")]
    end
    subgraph SERVING["서비스 제공 계층"]
        R[("Redis 캐시")]
        A["FastAPI"]
        N["Next.js"]
    end
    K --> C
    M --> C
    E --> C
    C --> O
    C --> P --> X --> Q --> W
    W --> T --> F
    PF -. "예약 / 재시도" .-> C
    PF -. "학습 / 평가" .-> CAL
    F --> CAL --> ES --> TR --> RK
    CAL --> MR
    RK --> MR
    CAL --> PR
    RK --> PR
    CAL -->|"모델 산출물"| O
    RK -->|"모델 산출물"| O
    MR -. "산출물 URI" .-> O
    PR --> R
    N --> A
    A --> R
    A --> PR
    A --> MR
```

## 기존 이벤트 연구의 핵심 흐름

### 수집

API → 수집기 → 불변 객체 → 메타데이터·아웃박스 → RabbitMQ → 정규화 → TimescaleDB

- 객체 쓰기가 성공하기 전에는 후속 작업을 발행하지 않는다.
- 메타데이터와 아웃박스 행은 하나의 PostgreSQL 트랜잭션으로 기록한다.
- 정규화기는 원본 해시와 변환 버전으로 중복 처리를 방지한다.
- 실패 메시지의 재시도 횟수와 오류를 기록하고 별도 실패 메시지 처리 정책으로 분리한다.

### 학습

Prefect → 기준시점 데이터셋 → 확률 보정·이벤트 연구 → 평가 → 모델 등록부

- 이벤트 단위 시간순 분할을 사용한다.
- `feature_as_of <= observed_at < resolved_at` 조건을 강제한다.
- 모델 바이너리는 객체 저장소에 저장하고 DB에는 URI와 체크섬을 기록한다.
- 검증 기준을 통과하지 못한 모델은 서비스 제공 상태로 승격하지 않는다.

### 결과 제공

Next.js → FastAPI → Redis → 예측·모델 메타데이터 DB

- 캐시에 없을 때 PostgreSQL을 조회하는 지연 로딩 캐시 방식을 사용한다.
- 학습은 API 요청 처리 경로에서 실행하지 않는다.
- 포트폴리오 요청은 입력 비중을 검증한 뒤 위험 계산 결과만 반환한다.

## 기존 이벤트 연구의 물리 구성 선택

| 논리 계층 | MVP 선택 | 도입 시점 |
|---|---|---|
| 원본·객체 저장소 | 현재 로컬 파일, 이후 MinIO/S3 | 3~4일차 프로토콜 |
| 메시지 브로커 | RabbitMQ | 아웃박스 이후 |
| 메타데이터 DB | PostgreSQL | 현재 스키마 존재 |
| 시계열 DB | TimescaleDB 확장 | 3~4일차 스키마 |
| 특징량 저장소 | SQL 스냅샷 테이블·뷰 | 3~4일차 |
| 작업 조율기 | Prefect | 수집 전체 흐름 검증 이후 |
| 모델 등록부 | PostgreSQL 메타데이터 + MinIO 산출물 | 3~4일차 계약 |
| 캐시 | Redis | FastAPI 부하 측정 이후 |
| API·화면 | FastAPI / Next.js | 분석 전체 흐름 검증 이후 |

상용 컨테이너 선택과 온라인 서빙 지연 방어는
[상용 전환 인프라와 실시간 서빙 전략](deployment-and-serving-strategy.md)에 정리한다.
AWS 데이터 계층이면 ECS/Fargate, GCP 데이터 계층이면 Cloud Run을 우선 검토한다.
Kubernetes는 MVP의 제외 범위를 유지하되, 운영 복잡도와 트래픽 규모가 실제로 확인된 뒤 재평가한다.

## 신뢰성 계약

- 전달 방식: 최소 한 번 전달을 가정한다.
- 멱등 키: `payload_hash + transformation_version + target_table`.
- 이벤트 시각: 원본 시각과 수집시각을 분리하고 UTC로 저장한다.
- 계보: 예측에서 특징량 스냅샷, 모델 버전, 원본 해시까지 역추적한다.
- 캐시: 만료시간을 사용하며 무효화 실패 시에도 DB 결과가 기준이다.
- 복구: 객체 저장소 원본에서 정제 데이터·특징량·예측을 재구축할 수 있어야 한다.

## 채택하지 않는 구성

- Kafka: 현재 처리량·운영 규모에 비해 복잡하며 원본 저장소에서 재처리할 수 있다.
- 별도 특징량 저장소 제품: SQL 스냅샷으로 온라인·오프라인 일관성을 먼저 검증한다.
- 별도 시계열 DB 클러스터: TimescaleDB로 PostgreSQL 운영 경계를 유지한다.
- Kubernetes: 로컬·공모전 MVP의 검증 범위 밖이다. 상용 전환 초기에는 ECS/Fargate 또는 Cloud Run의 관리형 컨테이너를 우선 검토한다.
- 서비스별 저장소: 하나의 모듈형 저장소와 분리 실행 가능한 작업 프로세스를 유지한다.

## 사용자 점검 항목

- [ ] RabbitMQ를 비동기 작업 브로커로 사용하는 데 동의하는가?
- [ ] 로컬에서는 MinIO, 운영에서는 S3 호환 저장소를 사용하는가?
- [ ] 시계열 데이터와 메타데이터를 한 PostgreSQL·TimescaleDB 계열로 운영하는가?
- [ ] 별도 특징량 저장소 제품은 온라인 추론 요구가 생길 때까지 보류하는가?
- [ ] Redis 도입을 FastAPI 성능 측정 이후로 미루는가?
- [ ] 모델 바이너리는 객체 저장소에, 버전·지표는 PostgreSQL에 저장하는가?
- [ ] 3~4일차는 프로토콜·스키마·기준 모델까지 구현하고 전체 인프라 실행은 후속으로 두는가?
- [ ] 상용 전환 시 AWS ECS/Fargate와 GCP Cloud Run 중 데이터 계층·팀 운영 역량에 맞는 하나를 선택했는가?
- [ ] API와 작업 프로세스의 확장 지표를 CPU만이 아니라 요청 동시성·큐 backlog로 측정하는가?
- [ ] Redis 캐시 미적중, DB timeout, 오래된 응답, cache stampede를 부하 테스트했는가?

## 참고 문서

- [TimescaleDB 하이퍼테이블](https://docs.timescale.com/use-timescale/latest/hypertables/)
- [Prefect 작업 흐름](https://docs.prefect.io/latest/tutorial/flows)
- [RabbitMQ 신뢰성](https://www.rabbitmq.com/docs/reliability)
- [MinIO S3 호환 저장소](https://min.io/docs/minio/linux/index.html)
- [Redis 클라이언트 캐시](https://redis.io/docs/latest/develop/clients/client-side-caching/)

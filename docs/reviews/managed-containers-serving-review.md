# 관리형 컨테이너와 온라인 서빙 전략 리뷰

작성일: 2026-09-22

## 이번 요청에서 완료한 범위

- Kubernetes를 MVP에서 제외하는 원칙을 유지하면서 AWS ECS/Fargate와 GCP Cloud Run을 비교했다.
- 관리형 컨테이너 선택 기준, 자동 확장 지표, readiness, 점진 배포, 회로 차단기·rollback,
  expand-contract 마이그레이션을 문서화했다.
- FastAPI 온라인 서빙에서 SQL 스냅샷과 Redis 지연 로딩 캐시를 분리하는 흐름을 정리했다.
- 캐시 미적중에 대한 단일 비행, 오래된 응답을 허용하는 최신화, 타임아웃 예산, DB pool 격리,
  명시적 상태 응답 전략을 추가했다.
- 데이터 분석 방법론에 데이터 단위, `source_time`·`available_at`·`observed_at`·
  `resolved_at`·`collected_at`, 확률 보정, 이벤트 연구, 위험 계산, 온라인 서빙 검증을 정리했다.
- 아키텍처, 의존성, 인프라 README, 프로젝트 명세에 새 전략 문서를 연결했다.

## 변경 문서

- `docs/deployment-and-serving-strategy.md`: 관리형 컨테이너와 온라인 서빙 운영 기준
- `docs/methodology.md`: 데이터 분석과 오프라인·온라인 분리 방법론
- `docs/architecture.md`: 상용 전환·캐시 미적중 점검 항목
- `docs/dependencies.md`: 관리형 컨테이너와 Redis 운영 의존성 기준
- `infra/README.md`: 배포·서빙 전략 연결
- `shockgraph-ai-project-spec.md`: 후속 구현 범위와 Kubernetes 제외 원칙

## 의도적으로 구현하지 않은 범위

- AWS·GCP 계정, Terraform, Docker 배포 리소스, 운영 비밀값
- ECS/Fargate 또는 Cloud Run 실제 배포
- Redis·PostgreSQL 운영 서버와 네트워크 구성
- FastAPI endpoint, 캐시 adapter, single-flight 코드
- 부하 테스트 도구와 SLO 확정

이번 변경은 운영을 바로 시작하는 코드가 아니라, 데이터와 모델 검증 후 상용 전환할 때의
선택 기준과 테스트 계약을 정리한 것이다.

## 검증 결과

- 문서 상대 링크와 Markdown 코드 블록 검증: 통과
- 기존 Python 품질 검사: Ruff 통과
- 기존 타입 검사: Pyright 오류 0개
- 기존 테스트: 42개 통과
- `git diff --check`: 통과

## 사용자 점검 항목

- [ ] 데이터 계층을 AWS로 둘 경우 ECS/Fargate를 기본 후보로 정할 것인가?
- [ ] GCP를 선택할 경우 Cloud Run의 최소·최대 인스턴스와 동시 요청 제한을 어떤 값으로 시작할 것인가?
- [ ] API 전체 p95 500ms를 초기 성능 가설로 사용할 것인가?
- [ ] 캐시 미적중에서 허용할 오래된 결과 기간과 `pending` 전환 기준을 정했는가?
- [ ] Redis lease와 오래된 결과 최신화를 FastAPI 구현 범위에 포함할 것인가?
- [ ] 큐 backlog, DB pool, API p95를 함께 보는 부하 테스트를 언제 진행할 것인가?

## 다음 구현 후보

- FastAPI 분석 응답 계약과 `ready`·`stale`·`pending`·`unsupported` 상태 모델
- PostgreSQL 스냅샷 조회 저장소와 인덱스 실행 계획 확인
- Redis cache-aside 어댑터, 버전형 키, 단일 비행 lease
- DB timeout·Redis 장애·동시 미적중 테스트
- Docker health/readiness와 managed container staging 배포 예제

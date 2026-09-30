# 인프라 영역

분석 기능의 전체 처리 흐름을 검증한 뒤 배포 구성을 시작한다.

2026-10-01 배포 설계는 Nginx의 개발·운영 도메인 분리를 기준으로 한다.
환경별 앱·데이터·비밀값 격리와 운영 내부 blue/green 전환을 별도로 구성한다.
현재 Nginx·앱 Dockerfile·운영 배포 자동화는 미구현이다. 기존 Compose는 로컬 DB용이다.
첫 공개 서비스는 검증된 과거 연구 집계 조회이며 상세 배포 순서와 검증 기준은
아래 전략 문서의 「이번 배포의 확정 방향과 현재 구현 범위」를 따른다.

MVP는 로컬 Docker와 PostgreSQL·TimescaleDB 계약 검증에 집중한다.
상용 전환은 Kubernetes 운영을 전제로 하지 않고 AWS ECS/Fargate 또는 GCP Cloud Run의
관리형 컨테이너를 검토한다. 선택 기준, 무중단 배포, API 자동 확장, Redis 캐시 미적중
지연 방어는 [상용 전환 인프라와 실시간 서빙 전략](../docs/deployment-and-serving-strategy.md)을 따른다.

온라인 요청은 원본 데이터를 매번 재계산하지 않고 승인된 SQL 스냅샷과 Redis 지연 로딩
캐시 결과를 사용한다. DB timeout이나 오래된 결과만 남은 경우 예측값을 임의로 만들지 않고
`pending`, `stale`, `insufficient_data`, `unsupported` 상태를 반환한다.

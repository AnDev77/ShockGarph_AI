# 인프라 영역

분석 기능의 전체 처리 흐름을 검증한 뒤 배포 구성을 시작한다.

MVP는 로컬 Docker와 PostgreSQL·TimescaleDB 계약 검증에 집중한다.
상용 전환은 Kubernetes 운영을 전제로 하지 않고 AWS ECS/Fargate 또는 GCP Cloud Run의
관리형 컨테이너를 검토한다. 선택 기준, 무중단 배포, API 자동 확장, Redis 캐시 미적중
지연 방어는 [상용 전환 인프라와 실시간 서빙 전략](../docs/deployment-and-serving-strategy.md)을 따른다.

온라인 요청은 원본 데이터를 매번 재계산하지 않고 승인된 SQL 스냅샷과 Redis 지연 로딩
캐시 결과를 사용한다. DB timeout이나 오래된 결과만 남은 경우 예측값을 임의로 만들지 않고
`pending`, `stale`, `insufficient_data`, `unsupported` 상태를 반환한다.

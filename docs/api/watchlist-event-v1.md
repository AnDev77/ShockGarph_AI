# 관심 자산과 사건 카드 API 계약

작성일: 2026-10-27. 첫 지원 자산은 QQQ·SPY다. 종목 보유 인증이 아닌 관심 목록이며 회원별 기록이다. 실제 투자 조언·주가 예측 응답은 포함하지 않는다.

## 요청과 응답

| 경로 | 동작 | 인증 |
|---|---|---|
| `GET /health/live` | 프로세스 생존만 확인, DB 상태 확인 아님 | 없음 |
| `GET /v1/me/watchlist` | 본인 종목 목록 | Bearer JWT |
| `POST /v1/me/watchlist` | `{"symbol":"QQQ"}` 추가, 동일 요청 반복 가능 | Bearer JWT |
| `DELETE /v1/me/watchlist/{symbol}` | 본인 목록에서 제거 | Bearer JWT |
| `GET /v1/me/events` | 본인 관심 종목과 연결된 공식 발표 예정/발표 카드 | Bearer JWT |

목록과 사건 조회에서 `member_id`는 요청 본문·경로·쿼리로 받지 않는다. 검증된 JWT의 양수 숫자 `sub`로만 결정한다. 서명 알고리즘 HS256, 만료·발행 시각을 검사하며 비밀값을 소스나 문서에 저장하지 않는다. 현재 doChallenge JWT의 발급 형식을 읽어 맞췄다. 두 서비스에 같은 검증 비밀값을 안전하게 제공해야 실제 연동된다. 현재 토큰에 issuer·audience 클레임이 없으므로 서비스 경계 운영 전에 발급·검증 계약을 정하고 키 회전 및 회원 삭제 동기화를 검토해야 한다.

사건 카드의 `scheduled_at`, `released_at`, `available_at`은 UTC다. 원문이 보관·확인되어 이용 가능해진 시각 전에는 `status=scheduled`, `release_url=null`로 응답한다. 서버의 현재 시각으로만 평가하며 클라이언트가 미래 시각을 입력해 공개를 앞당길 수 없다. 공식 발표 관계가 등록되지 않은 종목에는 빈 배열을 반환한다. 가격 수치나 인과 설명은 없다.

## 실행 전 조건

`infra/postgres/migrations/0003_watchlist_events.sql`을 실제 PostgreSQL에 적용하고, `SHOCKGRAPH_POSTGRES_DSN` 및 32바이트 이상 `SHOCKGRAPH_JWT_SECRET`을 배포 환경에 제공한다. 실행은 `uvicorn shockgraph_api.app:create_app_from_env --factory`다. 빈 설정이면 시작을 거부한다. 실제 PostgreSQL 연결·마이그레이션, doChallenge와의 실토큰 연동, 공식 발표 수집, 공개 표시 권리는 아직 확인하지 않았다. 배포 전 HTTPS, JWT issuer/audience 및 별도 권한 경계, DB 장애의 상태 응답, 종목 추가 제한과 회원 삭제 처리도 검증해야 한다.

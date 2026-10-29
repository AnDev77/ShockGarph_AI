# 금융 Java와 ShockGraph API의 첫 연결 계약

작성일: 2026-10-28. **현재 코드와 목표 계약을 구분한다.** 이 문서는 두 서버의 실제 로그인 연동이나 Java 금융 회원 서비스 구현 완료를 뜻하지 않는다. 첫 배포에서 개인 노트·결제·계좌 연결은 제외한다. 제품 범위는 [1차 배포 계획](../finance-v1-2026-10-31-plan.md)을 따른다.

## 현재 구현된 경로와 응답

| 실행체 | 현재 경로 | 본문/응답의 핵심 | 인증·상태 |
|---|---|---|---|
| doChallenge Java | `POST /api/v1/auth/login` | 이메일·비밀번호 입력 → `{"success":true,"data":{"tokenType":"Bearer","accessToken":"<token>","expiresInSeconds":...},"error":null}` | 기존 운동 서비스 로그인. 금융 회원 서버의 배포 계약은 아직 아님 |
| ShockGraph FastAPI | `GET /v1/me/watchlist` | `{"symbols":["QQQ","SPY"]}` | Bearer 토큰 필수. 응답은 호출 회원의 DB 행만 조회 |
| ShockGraph FastAPI | `POST /v1/me/watchlist` | `{"symbol":"QQQ"}` → 현재 목록 반환 | 같은 회원·종목 재요청은 중복 행을 만들지 않음 |
| ShockGraph FastAPI | `DELETE /v1/me/watchlist/{symbol}` | 현재 목록 반환 | 다른 회원의 행을 삭제하지 않음 |
| ShockGraph FastAPI | `GET /v1/me/events` | `{"events":[{"source":...,"event_id":...,"title":...,"scheduled_at":...,"matched_symbols":[...],"source_url":...,"status":...,"released_at":...,"available_at":...,"release_url":...}]}` | 회원 관심 종목과 연결된 DB 사건만 조회. 공식 발표 자동 수집은 아직 없음 |

현재 FastAPI의 관심 종목 범위는 QQQ·SPY이고, JWT에서 숫자 양수 `sub`를 읽어 회원을 선택한다. 클라이언트가 회원 ID를 본문·경로·쿼리로 보내지 않는다. `scheduled_at`·`released_at`·`available_at`은 UTC를 나타내는 ISO 8601 시각이다. 자료가 아직 이용 가능하지 않으면 `status=scheduled`, `released_at=null`, `available_at=null`, `release_url=null`이다. 현재 오류는 인증 실패 401, 미지원 자산 422로 처리한다. DB 중단 시 명확한 503과 준비 상태 확인은 **목표**이며 아직 코드에서 보장되지 않는다.

## 첫 배포의 목표 경로와 소유권

| 외부 경로 예시 | 최종 담당 | 계약 상태 |
|---|---|---|
| `/api/v1/auth/login` | 금융 Java | 기존 doChallenge 로그인 코드 참조. 금융 실행체와 프록시 경로는 미구현 |
| `/api/v1/me/watchlist` `GET/POST/DELETE` | 금융 Java | 현재 FastAPI 경로의 의미를 유지하되 Java DB로 이전할 **목표**. 현재 Java 구현 없음 |
| `/api/v1/market/events?symbols=QQQ,SPY` | FastAPI | 공개 일정·자료 목록의 **목표**. 특정 회원의 관심 목록을 저장·조회하지 않음. 현재 구현 없음 |
| `/api/v1/market/events/{source}/{event_id}` | FastAPI | 공식 원문 링크·이용 시각·자료 부족 상태가 있는 상세의 **목표**. 현재 구현 없음 |
| `/api/v1/community/rooms/{symbol}/messages` 및 `/ws/**` | 금융 Java | QQQ·SPY 공개 읽기·로그인 쓰기의 **목표**. 기존 doChallenge 모임 방과 다름 |

홈의 전체 공식 일정은 익명 조회 가능하다. 로그인 뒤 맞춤 목록이 필요하면 Java가 자기 DB의 관심 종목을 읽고, FastAPI의 공개 종목 필터 결과와 조립한다. FastAPI에 회원 관심 목록 사본을 계속 쓰거나 Java가 분석 DB를 직접 조회하지 않는다. 화면에 단일 도메인을 제공하는 게이트웨이의 실제 rewrite/strip-prefix 설정과 CORS는 배포 PR에서 시험한다. 표의 외부 경로는 예약 이름이므로 현재 실행 경로와 혼동하지 않는다.

## 토큰과 서비스 호출

1. 현재 doChallenge JWT는 HS256으로 서명한 문자열 `sub`(회원 ID), `email`, `role`, `iat`, `exp`를 발급한다. 현재 FastAPI는 HS256 서명과 `sub`·`iat`·`exp`의 존재 및 만료를 확인한다. 합성 Java 형식 토큰 시험과 CI PostgreSQL 시험은 통과했지만, **실제 Java 서버가 발급한 토큰으로 FastAPI를 호출한 통합 시험은 없다.**
2. 목표 계약은 발급자 `iss`, 대상 `aud`, 짧은 만료, 키 식별·교체, 탈퇴/차단 회원의 권한 종료를 포함한다. 구현 전에는 임의 `iss`·`aud` 값을 정답인 것처럼 쓰지 않는다. 서명 검증만으로 회원의 현재 상태를 확인했다고 주장하지 않는다.
3. Java→FastAPI 내부 조회가 생겨도 사용자 JWT를 무분별하게 전달하지 않는다. 공개 자료는 공개 API에서 조회하고, 비공개 분석은 별도 서비스 인증·권한 확인 계약을 만든다. 토큰·키·개인 정보는 URL, Kafka 메시지, 공개 로그에 싣지 않는다.

## 관심 목록 이전과 장애 처리

- 임시 소유자: 현재 PR #11의 FastAPI PostgreSQL `watchlist_assets(member_id,symbol)`. 최종 소유자: 금융 Java DB. Java 금융 회원 ID가 기존 숫자 회원 ID와 동일하다는 가정은 실제 회원 이전 시험 전까지 하지 않는다.
- 이전 절차: 회원 ID 대응표·삭제 회원을 확인 → FastAPI 목록 쓰기를 잠시 중지 → 회원별 행을 Java에 중복 없이 적재 → 회원별 종목 집합·삭제 상태를 비교 → API 라우트를 Java로 전환 → 새 쓰기 1건과 재시도를 시험. 실패하면 기존 경로로 복귀하되 전환 뒤 새 쓰기가 생겼다면 먼저 차이를 확인한다. 두 저장소에 동시에 쓰는 임시 해결책은 사용하지 않는다.
- 회원 삭제/차단: Java가 신원 상태를 소유한다. FastAPI 임시 회원 API는 삭제 회원의 기존 서명 토큰을 즉시 차단하는 경로가 없으므로 실토큰 연동과 탈퇴/차단 동기화 없이는 운영 준비 완료가 아니다.
- 실패 응답: 인증 실패는 401, 지원하지 않는 종목은 422. DB 중단·내부 조회 실패는 목표 계약에서 503 또는 명시된 `unavailable`로 표시하고 다른 회원 데이터나 빈 목록으로 성공을 위장하지 않는다. 공식 자료 원문이 미수집이면 예정 상태와 출처만 보여준다.

## 완료 시험과 남은 입력

두 실제 서버를 띄워 Java 로그인→FastAPI 임시 목록 조회→다른 회원 토큰 거부, 만료·위조·키 교체·삭제 회원, Java로의 목록 이전 전후 동일 결과, 한쪽 DB 중단, 공개 일정의 미래 원문 비노출을 검증해야 한다. 금융 Java 실행체, 운영 PostgreSQL 접속, 공식 사건 원본, 게이트웨이 설정은 아직 없다. 첫 배포의 제품 성공·모델 성능은 이 문서나 합성 계약 시험만으로 주장하지 않는다.

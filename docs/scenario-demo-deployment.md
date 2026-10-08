# 시나리오 분석 데모의 배포와 완료 기준

## 공개 범위

첫 공개는 독립 합성 자료를 쓰는 시나리오 체험 서비스다. 실제 Kalshi·컨센서스·ETF 자료의
이용권이나 자산 예측력을 확보한 서비스로 소개하지 않는다. 합성 데모 배포는 모델 오차 개선을
기다릴 필요가 없지만, 실제 자료 공개에는 해당 이용권이 필요하다.

이번 조회 기능은 DB 없이 실행한다. DB 연결 확인을 했다고 보고하지 않는다.
계정·포트폴리오 저장을 추가할 때 영속 저장소를 붙인다.

## 이번 주 완료 순서

| 단계 | 목표일 | 완료 기준 |
| --- | --- | --- |
| 화면과 API | 2026-10-06~07 | 세 시나리오·두 ETF·두 구간 동작, 데모 표시, 실제 연결 대기, 연구 노트 분리 |
| 공개 서비스 연결 | 2026-10-08 | Render API·Vercel 웹 URL, HTTPS, 동일 출처 API, 오류 화면 확인 |
| 설명과 시연 | 2026-10-09 | README·아키텍처·검증 한계·포트폴리오 스토리와 공개 링크 점검 |

날짜는 목표 일정이다. 설정 파일을 작성한 것과 실제 공개 배포를 구분해 기록한다.

## Vercel과 Render 연결

1. 이 변경이 포함된 GitHub 브랜치를 Render의 새 Blueprint에 연결한다.
   저장소 루트의 `render.yaml`이 `apps/api/Dockerfile`을 사용한다.
   `SHOCKGRAPH_SERVICE_MODE=demo`, 준비 상태 경로 `/health/ready`로 실행한다.
2. API의 실제 HTTPS URL을 확인한다. 다음 응답이 나와야 한다.
   `/health/ready`: `scope=synthetic_scenario_demo`.
   `/v1/scenarios/cpi?source=demo`: `source_kind=synthetic`.
   `/v1/scenarios/cpi?source=actual`: `status=pending`, 빈 `scenarios`.
3. Vercel에 같은 저장소를 연결하고 Root Directory를 `apps/web`, 프레임워크를 Next.js,
   Node.js를 22로 선택한다. 설치 `npm ci`, 빌드 `npm run build`를 사용한다.
4. Vercel의 서버 환경변수 `SHOCKGRAPH_API_URL`에 API 원점만 설정한다.
   예: `https://<실제 API 호스트>`. 경로·쿼리·비밀번호는 포함하지 않는다.
   운영과 미리보기 환경이 서로 다른 API를 쓰면 각 환경의 변수로 분리한다.
5. 웹의 `/api/v1/scenarios/cpi?source=demo`와 `/methodology`를 확인한다.
   브라우저는 동일 출처 프록시를 사용하므로 API 키나 원격 API 주소를 전달하지 않는다.
6. 브라우저에서 API를 직접 호출하는 별도 클라이언트가 있다면
   `SHOCKGRAPH_WEB_ORIGINS`에 실제 웹 원점을 정확히 등록한다. 현재 웹은 서버 프록시를 쓴다.

Render의 `checksPass`는 연결한 브랜치의 CI 검사 통과 후 자동 배포를 요청한다.
Vercel의 Git 배포는 계정에서 연결해야 한다. 저장소에 서비스 연결이 없으면 설정 파일만으로
URL이 생기지 않는다. 유료 리소스를 만들거나 기존 서비스를 바꾸는 작업은 이번 로컬 작업에
포함되지 않았다.

## 컨테이너 실행과 Nginx

```bash
docker compose -f compose.demo.yml up --build -d
docker compose -f compose.demo.yml exec -T gateway nginx -t
docker compose -f compose.demo.yml down
```

`compose.demo.yml`은 기존 PostgreSQL 개발 Compose와 별개다. API·웹 포트는 내부에만
노출하고 Nginx는 `127.0.0.1:8080`에 바인딩한다. 로컬 데모용 HTTP이며 공개 HTTPS 설정이 아니다.
API와 웹 이미지는 일반 사용자로 실행한다. Python 런타임 의존성은 `uv.lock`에서 내보낸
`infra/requirements-runtime.txt`의 버전·해시로 설치한다. 새 운영 라이브러리를 추가하지 않았다.

자체 호스팅에서 개발·운영 컨테이너를 나누려면 서로 다른 Compose 프로젝트와 포트를
사용하고, 외부 Nginx의 도메인·인증·TLS·네트워크를 별도로 구성한다. 예를 들어 개발 데모는
프로젝트 `shockgraph-dev`·8081, 운영 데모는 `shockgraph-demo`·8080으로 시작할 수 있다.
개발 도메인의 접근 제한·TLS·호스트 장애 대응은 이 로컬 설정에 구현됐다고 주장하지 않는다.
첫 Vercel·Render 경로는 관리형 HTTPS와 환경 설정을 사용하며 사용자 관리 Nginx를 강제하지 않는다.

## CI와 검증 범위

기존 GitHub Actions에 `feat/scenario-risk`와 `main`을 추가했다. Python 품질 검사·테스트,
웹 타입 검사·빌드 후 컨테이너 빌드, Nginx 검사, HTTP 준비 상태와 출처 분리를 확인하도록
구성했다. 실제 데이터 수집 작업의 이용 허가 게이트는 유지한다.

Docker가 없는 현재 작업 환경에서는 컨테이너 이미지 빌드와 Nginx 실행 검증을 수행하지
못했다. 새 컨테이너 CI도 아직 원격에서 실행하지 않았다. 공개 URL·인증서·클라우드 복구
동작은 서비스를 연결한 뒤 검증한다.

## 실제 자료로 전환할 때

`SHOCKGRAPH_SCENARIO_DATASET`은 `cpi-scenario-input-v1` JSON을 가리킨다.
입력 계약은 `packages/event_study/shockgraph_analytics/scenarios.py`에 있다.
발표 전 컨센서스·다중 임계값 호가, 가용시각과 원본 해시를 가진 과거 사건별 수익률이 필요하다.
실제 입력은 `source_kind=licensed_historical`, 공개 이용 허가 확인 기록
`publication_authorized=true`, `authorization_reference`를 요구한다.
이 값은 이미 확보한 실제 허가를 기록할 뿐 권한을 만들어내지 않는다.

관측 기준 시각과 발표시각, UTC, 중복 사건, 결과·수익률 가용시각, 정확한 컨센서스 인접 경계,
확률 단조성·보정량을 검증한다. 잘못된 실제 파일을 데모로 대체하지 않는다.
컨테이너에는 실제 원본을 포함하지 않았으므로 허가된 파일을 별도로 연결해야 한다.

## 공식 자료

- [Render Blueprint 설정](https://render.com/docs/blueprint-spec)
- [Render 준비 상태 검사](https://render.com/docs/health-checks)
- [Next.js 요청 처리](https://nextjs.org/docs/app/api-reference/file-conventions/route)

# 시장 기대·자산 반응 대시보드 작업 리뷰

작성일: 2026-10-06. 브랜치: `feat/analytics`.

## 이번에 사용할 수 있게 된 기능

기존 CPI·ETF 과거 평가를 화면에 연결했다. Next.js·Chakra UI로 밝은 금융 서비스
대시보드를 구현했다. 왼쪽 메뉴, 세 가지 요약, CPI 확률 오차 비교, 어두운 시장 기대
브리핑, 사용자 선택 자산 분석, 근거 노트를 배치한다. 모바일에서는 한 열로 바뀐다.

- 관심 자산 SPY·TLT와 발표 후 5분·30분을 선택해 해당 보고서를 조회한다.
- 기존 과거 발생비율과 Kalshi 확률의 Brier·CRPS를 같은 척도의 막대로 비교한다.
- 숫자 옆에 시험 사건 수, 점수 차이, Bootstrap 구간, 주요 평가 표본 게이트를 표시한다.
- 새로고침은 연결된 API를 다시 조회하며 선택 변경 중 이전 요청을 취소한다.
- API 오류·미적재·조회 중 상태를 구분하고 잘못된 숫자를 화면에 표시하지 않는다.
- 현재 호가가 없으면 브리핑 확률과 발표시각은 생성하지 않는다.

참고한 [금융 서비스 화면 방향](https://dribbble.com/shots/25539906-Finance-Saas-web-UI-design)을
프로젝트의 평가 정보 구조에 맞게 구성했다. 유료 템플릿 소스를 복제하지 않았다.

## 연결한 데이터와 해석

| 항목 | 연결한 기존 자료 | 화면에서의 의미 |
|---|---|---|
| CPI 확률 | `docs/cpi-coverage-review.md`의 2026-09-26 집계 | T0.3 계약의 과거 예비 평가 |
| CPI 점수 | 시장 0.1005, 과거비율 0.2342, 비교 24건 | 이 표본에서 시장확률 오차가 작음 |
| ETF 반응 | `docs/paper/results/cpi-kalshi-ablation-2026-09-30.json` | SPY·TLT × 5분·30분의 과거 탐색 평가 |
| ETF 표본 | 공통 사건 24건, 초기 학습 5건의 시험 19건 | 새 독립 사건을 늘린 것이 아님 |
| 주요 평가 | 초기 학습 20건의 시험 4/10건 | 주요 평가 게이트 미달 |
| 현재 CPI 호가 | 아직 연결되지 않음 | 현재 확률·호가시각·발표시각은 대기 |

CPI 집계는 문서에 기록된 소수 4자리 수치를 별도 JSON으로 옮긴 것이다.
`recorded_aggregate`, `decimal_places=4`, `recomputed=false`로 출처를 명시하며 원본에서
다시 계산한 감사 결과라고 주장하지 않는다. 유효한 원본 연구 스냅샷을 연결하면 이를 우선한다.

ETF 네 조합 모두 CRPS 차이 `Kalshi − 과거비율`가 양수이고 Bootstrap 구간이 0을
포함한다. 자산 예측의 추가 효과가 확인됐다는 문구를 표시하지 않는다. CPI와 ETF의
24건은 같은 사건 집합을 뜻하지 않는다. 현재 호가·미래 자산 수익률·투자수익과 구분한다.

## 코드 구조

- `apps/api/shockgraph_api/app.py`: 문서 집계 로딩과 출처, 점수 기반 CPI 결론,
  시험의 초기 학습 건수, 현재 호가 대기 응답.
- `apps/web/components/dashboard.tsx`: API 응답 검증, 자산·기간 선택, 요청 취소,
  새로고침, 비교 막대, 표본 게이트, 오류·대기 상태.
- `apps/web/app/globals.css`: 데스크톱·모바일 배치, 선택·키보드·터치 상태.
- `.github/workflows/alpaca-cpi-validation.yml`: 웹 타입 검사·빌드 작업과 API·웹 변경 감지.
- `Makefile`의 `api-review`: 외부 요청과 키 없이 기존 보고서로 API 실행.
- `scripts/export_dashboard_review_data.py`: API의 읽기 경계를 통해 기존 보고서만 내보냄.
- `apps/web/scripts/export-preview.cjs`: 같은 React 컴포넌트와 Chakra 스타일로 미리보기 생성.
- `apps/web/scripts/preview-controls.js`: 미리보기의 네 조합 선택. 외부 요청 없음.
- `docs/ui/market-expectation-dashboard.html`: 저장된 집계 기반의 독립 실행 미리보기.

내보내기 도구는 이미 설치되는 TypeScript·React·Next.js의 PostCSS를 재사용한다.
새 운영 의존성을 추가하지 않았다. 미리보기는 정적 과거 기록이며 새로고침·실시간 API
연동은 원래 웹 앱에서 실행한다.

## 검증 결과와 제한

- `make PYTHON=.venv/bin/python quality`: Ruff 통과, Pyright 오류·경고 0.
- `make PYTHON=.venv/bin/python test`: **153개 통과**, Starlette의 기존 폐기 예정 경고 1건.
- `npm --prefix apps/web run typecheck`: 통과.
- `npm --prefix apps/web run build`: 통과.
- `npm --prefix apps/web ci --dry-run --ignore-scripts --offline --no-audit --no-fund`: 통과.
- 첫 원격 CI의 API 검사 통과. 웹 검사는 기존 원격 잠금파일 오류를 발견해 후속 수정했다.
- API 준비 상태와 Next.js 개발 서버의 HTTP 200 및 화면 제목 확인.
- 미리보기의 네 조합 선택: 별도 Node 점검에서 보고서 수치·표시 자산·선택 상태 일치.
- 미리보기 생성: 실제 React 컴포넌트 렌더링 성공, 외부 API 호출 없음.

브라우저는 로컬 주소와 파일 주소를 정책상 열 수 없었고, Chromium 다운로드도 네트워크
허용 목록으로 차단됐다. 따라서 실제 브라우저의 픽셀 배치·모바일 가로 넘침·키보드 이동을
실측했다고 주장하지 않는다. 대화 미리보기와 아래 사용자 점검으로 화면을 확인해야 한다.
초기 `next start` HTTP 점검은 실패했고, 문서에서 권장하는 `npm run dev`로 HTTP 200을
확인했다. 운영 실행은 기존 standalone 컨테이너 경로를 따른다.

이번에는 새로운 모델을 학습하거나 Kalshi 원본을 재수집하지 않았다. 예측 성능 개선과
실시간 서비스 배포를 완료했다는 의미가 아니다.

## 사용자가 우선 확인할 사항

1. **첫 인상**: 평가 결과를 보는 화면이라는 점과 현재 호가 대기 상태가 명확한가?
2. **선택 동작**: SPY → TLT, 5분 → 30분을 바꾸면 이름·구간·CRPS가 함께 바뀌는가?
3. **연구 해석**: CPI 정확도가 좋아도 자산 예측 효과는 확인되지 않았다는 구분이 읽히는가?
4. **작은 화면**: 휴대폰 너비에서 글자·막대·선택 버튼이 잘리고 가로 스크롤이 생기지 않는가?
5. **연결 오류**: API를 끈 뒤 새로고침하면 기록 연결 안내가 표시되고 예전 숫자를 남기지 않는가?

실행 명령은 [웹 안내](../../apps/web/README.md), API 계약은
[API 안내](../../apps/api/README.md)에 정리했다.

## 다음 완료 단위

현재 호가를 제품에 사용할 수 있는 이용 권한과 공급 경계를 확인한 뒤, 기준시각·만료·오래된
호가 상태를 포함한 시장 브리핑을 연결한다. 사용자 화면 검토 후 Nginx 개발·운영 분리와
기존 컨테이너 경로의 배포 확인을 진행한다. DNN·곡률·채팅방은 이번 배포 범위 밖에 둔다.

## 웹 CI에서 발견한 기존 설치 문제

첫 푸시의 Actions 실행 `37423791581`에서 `validate`는 통과했지만 `web`의 `npm ci`가
EUSAGE로 실패했다. 기존 원격 `package-lock.json`은 JSON으로 읽히지 않는 내용이었다.
원격 파일을 처음에는 보존했으나 신규 웹 CI가 문제를 드러냈다. 로컬에서 검증한
lockfileVersion 3의 JSON 잠금파일을 UTF-8로 정상 반영한다. 설치 기준이 되는 버전은
Next.js 16.3.6, Chakra UI 3.37.0, React 19.3.0이며 현재 manifest 범위에 들어간다.
별도 원인은 [웹 설치 트러블슈팅](../troubleshooting/web-dependency-lockfile.md)에 정리했다.

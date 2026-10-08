# 포트폴리오 이벤트 영향 대시보드

Next.js·Chakra UI와 FastAPI를 사용한다. SPY 비중과 선택적 USD 평가액을 입력하면
TLT 잔여 비중과 CPI 발표 후 5분·30분의 포트폴리오 평균 변화·상승/하락/보합 추정확률·
분위수 범위를 표시한다. 시나리오 근거는 접힌 상세 영역, 연구 기록은 `/methodology`에 둔다.
현재 데모는 독립적으로 만든 합성 사건 36건이며 실제 포트폴리오 자료는 연결 대기다.

## 로컬 실행

저장소 루트에서 Python 개발 의존성을 설치한 뒤 두 터미널에서 실행한다.

```bash
make PYTHON=.venv/bin/python api-demo
npm --prefix apps/web ci
npm --prefix apps/web run dev
```

PowerShell의 API 터미널에서는 다음과 같이 실행한다.

```powershell
$env:SHOCKGRAPH_SERVICE_MODE="demo"
.\.venv\Scripts\python.exe -m uvicorn shockgraph_api.app:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

웹은 `http://localhost:3000`이다. 브라우저는 동일 출처 `/api`로 요청하고 Next.js 서버가
FastAPI의 허용된 GET 경로로 전달한다. 개발 API 기본값은 `http://127.0.0.1:8000`이며
다른 주소는 서버 환경변수 `SHOCKGRAPH_API_URL`에 설정한다. 배포에서는 이 변수가 필수다.
기존 `NEXT_PUBLIC_API_BASE_URL`은 현재 프록시 설정에 사용하지 않는다.

## 입력과 자료 상태

- 화면 SPY 비중은 0–100% 정수, TLT는 나머지이며 합계 100%다.
- USD 평가액은 선택적이고 0–1조 범위다. 비우면 변화율만 표시한다.
- 비중·구간·자료 모드 변경 시 이전 결과를 숨기고 요청을 취소한다.
- 실제 모드에 자료가 없으면 연결 대기, 양의 확률이 있는 시나리오의 표본이 부족하면
  전체 결과 보류다. 누락된 자료를 제거해 재정규화하거나 데모로 대체하지 않는다.
- 자료 출처·요청 비중·확률 합·분위수 순서·금액·자산 기여를 표시 전에 검사한다.
- FOMC·원유재고는 준비 중이다. 실시간 시장자료나 검증된 예측 성능을 제공한 상태가 아니다.

## 검증과 미리보기

```bash
npm --prefix apps/web run typecheck
npm --prefix apps/web run check:contract
npm --prefix apps/web run build
npm --prefix apps/web run preview:export
```

응답 계약 검사와 미리보기는 Python 개발 의존성이 필요하다. Python 경로가 다르면
`PREVIEW_PYTHON`을 지정한다. 기본 경로는 `.venv/bin/python`이다.
내보낸 `docs/ui/portfolio-risk-dashboard.html`은 같은 React 컴포넌트와 API 계산을 사용한다.
6가지 예시 비중·두 구간·합성/실제 대기 상태를 전환한다. 직접 입력 필드는 미리보기에서
비활성이고 직접 비중·평가액 계산은 실행 앱에서 지원한다.

검증 범위와 한계는 [구현 리뷰](../../docs/reviews/portfolio-risk-simulator-review.md)를 따른다.

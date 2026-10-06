# 시장 기대·자산 반응 대시보드

Next.js와 Chakra UI v3로 구현한 화면이다. CPI 계약 확률의 과거 Brier 평가와
SPY·TLT 수익률 분포의 과거 CRPS 평가를 별도로 보여준다. 사용자는 관심 자산과
발표 후 5분·30분 구간을 바꿀 수 있다. 현재 호가는 연결 대기로 표시한다.

## 기존 결과로 로컬 실행

저장소 루트에서 설치하고 API를 실행한다. 외부 데이터 수집이나 API 키가 필요하지 않다.

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
make PYTHON=.venv/bin/python api-review
```

다른 터미널에서 웹을 실행한다.

```bash
npm --prefix apps/web ci
npm --prefix apps/web run dev
```

`http://localhost:3000`을 연다. API 주소가 다르면 웹 실행 전에
`NEXT_PUBLIC_API_BASE_URL`을 지정한다. 기본값은 `http://localhost:8000`이다.
서버 허용 출처는 `SHOCKGRAPH_WEB_ORIGINS`에 쉼표로 구분한다.

PowerShell에서는 루트에서 다음과 같이 실행한다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:SHOCKGRAPH_RECORDED_CPI_SUMMARY = "docs/paper/results/cpi-probability-recorded-2026-09-26.json"
$env:SHOCKGRAPH_ABLATION_REPORT = "docs/paper/results/cpi-kalshi-ablation-2026-09-30.json"
.\.venv\Scripts\python.exe -m uvicorn shockgraph_api.app:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

다른 PowerShell에서 `npm --prefix apps/web ci`와 `npm --prefix apps/web run dev`를 실행한다.

## 실제 스냅샷 연결

원본에서 산출한 검증된 `metadata.json`이 있으면 `SHOCKGRAPH_RESEARCH_METADATA`로 연결한다.
이 스냅샷이 유효하면 기존 문서 집계보다 우선한다. 파일 교체 후 API를 재시작한다.

```bash
SHOCKGRAPH_RESEARCH_METADATA=/절대/경로/metadata.json \
SHOCKGRAPH_ABLATION_REPORT=/절대/경로/kalshi_ablation.json \
make PYTHON=.venv/bin/python api-dev
```

## 검증과 화면 미리보기

```bash
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
npm --prefix apps/web run preview:export
```

마지막 명령은 같은 React 컴포넌트와 API의 기존 보고서를 이용해
`docs/ui/market-expectation-dashboard.html`을 생성한다. 브라우저에서 직접 열 수 있다.
SPY·TLT와 5분·30분 선택은 포함된 네 조합의 기록을 바꿔 보여준다.
새로고침과 실시간 API 조회는 원래 앱에서 제공하며 내보낸 미리보기에는 포함하지 않는다.
Python 경로가 다르면 `PREVIEW_PYTHON`을 지정한다. 미리보기 생성에는 개발 의존성 설치가 필요하다.

CPI 점수는 `docs/cpi-coverage-review.md`에 기록된 소수 4자리 집계이며 이번 작업에서
원본을 재계산한 값이 아니다. ETF 점수는 저장된 2026-09-30 집계 보고서를 읽는다.
실시간 브리핑·알림 발송·미래 수익률 예측은 아직 연결되지 않았다.

# API 영역

검증된 연구 스냅샷만 읽는 FastAPI 경계를 구현한다. 요청 처리 중 수집·학습·금융 계산을
실행하지 않는다.

현재 엔드포인트:

- `GET /health/live`: 프로세스 생존 여부
- `GET /health/ready`: 검증된 연구 스냅샷 로딩 여부
- `GET /v1/assets`: SPY·TLT·GLD의 지원 범위와 데이터 상태
- `GET /v1/research/cpi-probability`: 검증된 CPI 확률 연구 결과
- `GET /v1/research/cpi-kalshi-ablation`: SPY·TLT 공통 사건의 확률 교체 비교 집계
- `GET /v1/analysis`: 자산·이벤트·기간 조합 결과. 실가격 미적재 시 수치를 생성하지 않고
  `insufficient_data`를 반환한다.

로컬 실행:

```bash
export SHOCKGRAPH_RESEARCH_METADATA=artifacts/paper-dataset/paper-event-v1/<실행-해시>/metadata.json
make PYTHON=.venv/bin/python api-dev
```

Kalshi 자산 비교 결과를 함께 표시하려면 Actions Artifact에서 `kalshi_ablation.json`을
내려받아 다음 환경변수를 설정하고 API를 다시 실행한다. 이 파일에는 집계 지표와 입력
해시만 있으며, API 키나 개별 가격은 포함하지 않는다.

```bash
export SHOCKGRAPH_ABLATION_REPORT=/절대/경로/kalshi_ablation.json
```

Windows PowerShell에서는 `$env:SHOCKGRAPH_ABLATION_REPORT = "C:\\경로\\kalshi_ablation.json"`을
사용한다. 설치 후 API에서 분석 패키지를 불러올 수 있도록 `pip install -e ".[dev]"`를
다시 실행한다. API는 시작 시 검증한 파일을 읽으며 파일 교체 후에는 재시작이 필요하다.

유효한 보고서가 있으면 `/v1/analysis`는 SPY·TLT에 대해 `exploratory` 상태와 실제 공통
사건 수·시험 수·진단 지표를 반환한다. GLD는 주 분석에 포함하지 않는다. 보고서가
손상되거나 표본 게이트와 상태가 맞지 않으면 전용 조회는 503을 반환한다.

API 문서는 실행 후 `http://127.0.0.1:8000/docs`에서 확인한다.

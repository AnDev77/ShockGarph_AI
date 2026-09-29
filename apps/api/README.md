# API 영역

검증된 연구 스냅샷만 읽는 FastAPI 경계를 구현한다. 요청 처리 중 수집·학습·금융 계산을
실행하지 않는다.

현재 엔드포인트:

- `GET /health/live`: 프로세스 생존 여부
- `GET /health/ready`: 검증된 연구 스냅샷 로딩 여부
- `GET /v1/assets`: SPY·TLT·GLD의 지원 범위와 데이터 상태
- `GET /v1/research/cpi-probability`: 검증된 CPI 확률 연구 결과
- `GET /v1/analysis`: 자산·이벤트·기간 조합 결과. 실가격 미적재 시 수치를 생성하지 않고
  `insufficient_data`를 반환한다.

로컬 실행:

```bash
export SHOCKGRAPH_RESEARCH_METADATA=artifacts/paper-dataset/paper-event-v1/<실행-해시>/metadata.json
make PYTHON=.venv/bin/python api-dev
```

API 문서는 실행 후 `http://127.0.0.1:8000/docs`에서 확인한다.

# 21일차 검증 결과 조회 API와 실데이터 실행 경로 리뷰

작성일: 2026-09-29

## 작업 결과

검증된 CPI 확률 연구 결과를 화면에 제공할 수 있는 읽기 전용 FastAPI 경계를 구현했다.
API 요청 중에는 외부 자료 수집이나 모델 학습을 실행하지 않는다. 실제 ETF 가격 자료가
없을 때는 예상수익률을 0으로 채우지 않고 `insufficient_data`와 원인을 반환한다.

| 경로 | 역할 |
|---|---|
| `apps/api/shockgraph_api/app.py` | 생존·준비 상태, 자산 지원 상태, CPI 확률 연구, 자산 분석 응답 |
| `tests/integration/test_analysis_api.py` | 검증 결과와 미완성 ETF 분석 구분, 미지원 조합, 잘못된 스냅샷 차단 |
| `scripts/run_cpi_asset_pipeline.py` | 과거 SIP 분봉 수집 → 사건 패널 → 가격 기준선 평가를 한 번에 실행 |
| `apps/api/README.md` | 환경변수와 로컬 실행 방법 |

## API 상태의 의미

| 상태 | 화면에서의 처리 |
|---|---|
| `ready` | 검증된 스냅샷과 표본 수·기준시각을 함께 표시 |
| `insufficient_data` | 가격 자료가 부족하다는 이유를 표시하고 예측 숫자를 숨김 |
| `unsupported` | 지원하지 않는 종목·이벤트·기간임을 표시 |
| `pending` | 연구 스냅샷이 로딩되지 않았음을 표시 |

현재 `/v1/research/cpi-probability`는 검증된 CPI `T0.3` 확률 평가를 제공할 수 있다.
`/v1/analysis`의 SPY·TLT·GLD 결과는 실제 가격 자료가 들어오기 전까지
`insufficient_data`다. CPI 발생확률을 ETF 상승확률로 표현하지 않는다.

## 키 발급 후 실행할 명령

키 값은 채팅·명령 인수·Git 파일에 저장하지 않고 실행 셸의 환경변수로만 설정한다.

```bash
export ALPACA_API_KEY_ID=<발급한-Key-ID>
export ALPACA_API_SECRET_KEY=<발급한-Secret-Key>

make PYTHON=.venv/bin/python research-cpi-asset-pipeline \
  RELEASE_CSV=artifacts/bls-cpi-vintages/<실행-해시>/release_vintage.csv \
  PROBABILITY_CSV=artifacts/paper-dataset/<실행-해시>/event_coverage.csv
```

성공하면 ETF 분봉 자료, CPI 공통 사건 패널, 가격 기준선 평가 보고서의 경로를 한 JSON으로
출력한다. 첫 실행에서는 출력 경로보다 HTTP 오류, 세 ETF별 봉 개수, 공통 사건 수를 먼저
확인한다.

## 직접 확인할 사항

- [ ] 발급한 값이 Trading API의 Key ID와 Secret Key 한 쌍인지 확인한다.
- [ ] 키를 저장소 파일이나 채팅에 붙여넣지 않는다.
- [ ] 첫 실제 실행에서 `feed=sip`와 과거 15분 제한 조건을 확인한다.
- [ ] `coverage.json`에서 자산·연도별 `missing_start_bar`, `missing_end_bar`를 확인한다.
- [ ] `metadata.json`의 `common_events`가 최소 평가 조건을 충족하는지 확인한다.
- [ ] 시험 사건이 10개 미만이면 ETF 성능 수치를 공개하지 않는다.
- [ ] 화면에서 CPI 확률과 ETF 자산 반응을 다른 지표로 표시한다.

## 검증 결과

- API 통합 테스트를 포함한 전체 테스트: 110개 통과
- Ruff 통과
- Pyright 오류·경고 0개
- Git 공백 검사 통과
- 실제 Alpaca 호출: 현재 ChatGPT 실행 환경에 키가 주입되지 않아 미실행

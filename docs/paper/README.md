# 논문 연구 패키지

작성일: 2026-09-26

이 디렉터리는 ShockGraph AI의 실험 코드와 논문 작성 자료를 연결한다. 현재 확인된
실증 결과는 Kalshi CPI `T0.3` 계약의 확률 평가, BLS 최초 발표 빈티지 대조와
ETF 실가격 표본 진단까지다. 가격 기준선만 평가했으므로 Kalshi를 추가한
자산 방향·수익률·위험 예측 성능은 주장하지 않는다. 주 분석 자산은 SPY·TLT이며,
GLD는 탐색적 보조 분석으로 둔다.

## 문서 구성

| 문서 | 목적 |
|---|---|
| [연구 프로토콜](research-protocol.md) | 연구 질문, 가설, 표본, 결과변수, 식별 한계 고정 |
| [데이터 사전](data-dictionary.md) | 원본·정제·분석 자료의 필드, 시각, 계보, 이용조건 정리 |
| [사전 분석 계획](analysis-plan.md) | 모델, 기준선, 지표, 강건성 검정, 중단 기준 고정 |
| [논문 구성안](manuscript-outline.md) | 제목, 초록 뼈대, 장별 논리, 표·그림 목록 정리 |
| [선행연구 지도](literature-map.md) | 기존 연구의 범위와 이 연구가 채워야 할 간격 정리 |

## 현재 확보한 데이터

| 단계 | 사건 수 | 상태 |
|---|---:|---|
| 결과가 확정된 고정 임계값 `T0.3` | 55 | 확보 |
| 계약 종료 직전 확률 품질 통과 | 29 | 확보 |
| 과거 사건 10개 이후 같은 사건 기준 비교 | 24 | 확보 |
| BLS 표준 월간 최초 발표 결합 | 53 | 확보·Kalshi 결과 전건 일치 |
| 비표준 발표 | 2 | 2025년 10월 발표 없음, 11월 2개월 누적 발표 제외 |
| SPY·TLT 두 구간 공통·Kalshi 유효 사건 | 27 | SIP 실데이터 진단, 20건 학습 후 시험 7건 |
| GLD 포함 세 ETF 공통 사건 | 11 | 탐색적 보조 표본 |

비표준 BLS 발표를 과거 기준선에서도 제거한 24개 비교 사건에서 원시 시장확률 Brier는
0.1005, 이전 표준 월간 결과의 누적 발생비율은 0.2342였다. 사건별 손실 차이의 평균은
-0.1337, paired bootstrap 95% 구간은 [-0.1876, -0.0857]이다. 이는 논문의 1단계
자료 적합성 결과이며 자산 반응에 대한 주요 가설 검정은 아니다.

## 논문용 데이터 생성

먼저 최신 실데이터 감사를 실행한다.

```bash
make PYTHON=.venv/bin/python research-audit-cpi
```

출력된 `report.json`을 명시적으로 지정해 사건 단위 논문 자료를 만든다.

```bash
python scripts/export_paper_dataset.py \
  --input artifacts/kalshi-cpi-audit/<실행-해시>/report.json \
  --output artifacts/paper-dataset
```

생성물은 다음 두 파일이다.

- `event_coverage.csv`: 포함·제외 사건을 모두 보존한 분석용 사건 표
- `metadata.json`: 원본 보고서 해시, 스키마 버전, 집계 지표, CSV 해시

두 파일은 원본 보고서 SHA-256 아래에 불변으로 생성된다. `artifacts/`는 Git에 넣지
않는다. Kalshi 확률·가격의 논문 부록 또는 공개 저장소 배포는 이용조건을 다시 확인한
뒤 결정한다.

BLS 최초 발표 자료를 대조한 뒤 이용권이 확인된 ETF 분봉과 결합한다.

```bash
make PYTHON=.venv/bin/python research-bls-cpi \
  AUDIT_REPORT=artifacts/kalshi-cpi-audit/<실행-해시>/report.json

export ALPACA_API_KEY_ID=<개인-연구용-키>
export ALPACA_API_SECRET_KEY=<개인-연구용-비밀키>
make PYTHON=.venv/bin/python research-alpaca-etf \
  RELEASE_CSV=artifacts/bls-cpi-vintages/<실행-해시>/release_vintage.csv

make PYTHON=.venv/bin/python research-asset-panel \
  RELEASE_CSV=artifacts/bls-cpi-vintages/<실행-해시>/release_vintage.csv \
  PROBABILITY_CSV=artifacts/paper-dataset/<실행-해시>/event_coverage.csv \
  ASSET_BAR_CSV=artifacts/alpaca-etf-bars/<실행-해시>/asset_minute_bars.csv
```

자산 패널은 발표 1분 전 종가를 시작값으로 두고 발표 후 5분·30분의 정확한 분봉만
사용한다. 가까운 시각으로 대체하거나 결측을 보간하지 않으며, SPY·TLT와 두 구간이 모두
존재하는 사건을 주 분석 공통 표본에 넣는다. 기존 세 ETF 패널은 보조 진단으로
유지한다. 기본 `ALPACA_FEED`는 `sip`이며 IEX 결과와 섞지
않는다. 키와 원시 가격은 커밋하지 않고, 시장자료 재배포 허가가 확인되기 전에는 파생
패널도 로컬 연구 전용으로 취급한다.

## 주장 등급

1. **현재 가능:** 공개 API 접근성, 표본 커버리지, `T0.3` 확률의 내부 기준 비교.
2. **추가 자료와 모델 검증 후 가능:** 기존 거시정보 대비 자산 수익률 분포 예측의 증분 가치.
3. **현재 금지:** CPI의 순수 인과효과, 거래 수익성, 상용 위험모델 수준, 다른 이벤트로의 일반화.

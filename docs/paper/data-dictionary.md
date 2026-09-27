# 논문 데이터 사전

## 데이터 계층

| 계층 | 파일 또는 원천 | 역할 | 공개 여부 |
|---|---|---|---|
| 원본 | Kalshi 현재·과거 시장과 1분 캔들 JSON | 확률·호가·거래량 근거 | 로컬 불변 저장, 공개 보류 |
| 원본 | BLS 과거 CPI 보도자료 또는 승인된 빈티지 | 최초 발표값·발표시각 | 출처 조건 확인 후 링크 중심 |
| 원본 | 이용권이 확인된 SPY·TLT·GLD 분봉 | 발표 전후 가격 | 원시 가격 공개 보류 |
| 정제 | `event_coverage.csv` | Kalshi 포함·제외와 확률 점수 | 로컬 연구 전용 |
| 정제 | `release_vintage.csv` | BLS 최초 발표값·시각과 Kalshi 결과 대조 | 출처 링크·파생값 공개 가능성 검토 |
| 외부 입력 | ETF 분봉 CSV | 사건·자산·분별 OHLCV와 가용시각 | 공급원 이용조건 확인 필요 |
| 분석 | `event_asset_panel.csv` | 확률·최초 발표·자산 구간 수익률 공통 입력 | 원시 가격 이용조건 검토 후 결정 |

## `event_coverage.csv` 스키마

| 필드 | 형식 | 의미 | 누수·품질 규칙 |
|---|---|---|---|
| `event_order` | 정수 | 계약 종료시각 기준 사건 순서 | 시간순 평가 고정 |
| `event_ticker` | 문자열 | CPI 발표 식별자 | 레거시 `CPI-*`와 `KXCPI-*` 보존 |
| `market_ticker` | 문자열 | `T0.3` 계약 식별자 | 사건당 하나, 중복 금지 |
| `tier` | 문자열 | `historical` 또는 `recent` | 올바른 API 경로 추적 |
| `cutoff_at` | UTC 시각 | Kalshi 거래 종료시각 | BLS 발표시각과 혼동 금지 |
| `outcome` | `yes`/`no` | 계약 정산 결과 | 평가 정답으로만 사용 |
| `outcome_binary` | 0/1 | Brier 계산용 정답 | `yes=1` |
| `status` | 범주 | 품질 포함·제외 상태 | 결측 보간 금지 |
| `candidate_candles` | 정수 | 조회된 1분 캔들 수 | 독립 표본 수가 아님 |
| `eligible_candles` | 정수 | 기본 호가·거래량 기준 통과 수 | 사건 내 품질 진단 |
| `near_release_candles` | 정수 | 종료 전 15분 내 유효 캔들 수 | 실제 BLS 발표와 별도 |
| `latest_eligible_end_at` | UTC 시각 | 마지막 유효 캔들 종료 | `cutoff_at` 이하여야 함 |
| `quote_end_at` | UTC 시각 | 확률에 사용한 캔들 종료 | 품질 통과 사건만 존재 |
| `probability_yes` | 0~1 | YES 매수·매도 중간값 | 사후 정산가격 사용 금지 |
| `spread` | 0~1 | YES 매도−매수 | 기본 상한 0.10 |
| `volume` | 비음수 실수 | 해당 1분 캔들의 거래량 | 양수만 확률에 사용 |
| `prior_events` | 정수 | 기준 확률에 사용한 이전 결과 수 | 현재·미래 결과 제외 |
| `expanding_historical_probability` | 0~1 | 이전 사건의 누적 YES 비율 | 최소 10개 이후 계산 |
| `market_brier_loss` | 0~1 | 시장확률 사건별 제곱오차 | 비교 가능한 사건만 존재 |
| `expanding_historical_brier_loss` | 0~1 | 누적비율 사건별 제곱오차 | 같은 사건 비교 |
| `brier_loss_difference` | 실수 | 시장 손실−기준 손실 | 음수이면 시장 우세 |

## 다음 결합 스키마

### `release_vintage.csv`

| 필드 | 의미 |
|---|---|
| `event_id` | 내부의 월별 CPI 발표 식별자 |
| `event_ticker` | Kalshi CPI 사건 식별자 |
| `reference_month` | CPI가 측정하는 연·월 |
| `release_at` | BLS 최초 공개 UTC 시각 |
| `actual_mom_first` | 최초 발표 계절조정 전월비 |
| `threshold` | 고정 임계값 0.3% |
| `bls_outcome` | 최초 발표값의 엄격한 `actual > 0.3` 결과 |
| `kalshi_outcome` | 계약 정산 결과 |
| `outcome_match` | 두 결과 일치 여부 |
| `source_url` | 공식 BLS 보도자료 아카이브 주소 |
| `raw_hash` | 원본 SHA-256 |

### ETF 분봉 외부 입력

| 필드 | 의미 |
|---|---|
| `asset_id` | `SPY`, `TLT`, `GLD` 중 하나 |
| `price_at`, `available_at` | UTC 분 시각과 관측 가능 시각 |
| `open`, `high`, `low`, `close` | 양수이며 OHLC 범위가 일관된 가격 |
| `volume` | 비음수 거래량 |
| `extended_hours` | 장전 자료 포함 여부, 현재 사건창에서는 참이어야 함 |
| `raw_hash` | 가격 원본 SHA-256 |

### `event_asset_panel.csv`

사건 식별자·최초 발표값·Kalshi 확률에 자산과 `m5`·`m30` 구간을 결합한다. 시작가는
`release_at - 1분`, 종료가는 `release_at + 구간`의 종가다. 정확한 시각이 없으면
가까운 관측값으로 대체하지 않는다. 세 자산과 모든 구간이 갖춰진 사건만 분석 표본에
포함하고, 제외 사유는 `coverage.json`에 남긴다.

## 시각과 빈티지 규칙

`cutoff_at`, `release_at`, `price_at`, `available_at`, `collected_at`은 모두 UTC로 저장한다.
최초 발표 CPI와 현재 BLS 시계열은 같다고 가정하지 않는다. 계절조정 계열은 최근 5년이
연례 재계산될 수 있으므로 과거 당시 값이 필요한 주 분석에서는 보도자료 또는 ALFRED
빈티지를 사용한다. 현재 시계열은 강건성 분석에만 둔다.

## 계보와 동결

논문 실행 하나는 다음을 고정한다.

- 원본 파일별 SHA-256
- 변환 코드 Git 커밋
- 데이터 스키마 버전
- 포함·제외 규칙 버전
- 모델 설정과 난수 시드
- 표·그림 생성 스크립트 버전

현재 내보내기는 `paper-event-v1`, `cpi-release-vintage-v1`,
`cpi-event-asset-panel-v1`이다. 입력·CSV 해시가 `metadata.json`에 기록되며 기존
내용과 다른 파일을 같은 해시 경로에 덮어쓰지 않는다.

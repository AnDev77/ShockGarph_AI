# CPI 서비스 데이터 연결과 점검 안내

작성일: 2026-10-11, 한국 시각.

## 이번 기능의 역할

이미 로컬에 보관했고 이용 범위를 확인한 자료를 API용 사건 스냅샷으로 변환한다.
외부 API를 호출하거나 키를 읽거나 모델을 훈련하지 않는다. 기존 Brier·CRPS 집계에서
사건별 공동수익률을 복원할 수 없으므로 집계 보고서는 이 변환기의 입력이 아니다.

| 설정 필드 | 필요한 입력 | 점검할 사항 |
| --- | --- | --- |
| `release_csv` | 기존 `release_vintage.csv` | 최초 CPI 발표값·발표 시각·BLS 과거 발표 출처·원본 해시 |
| `asset_bar_csv` | 기존 `asset_minute_bars.csv` | 같은 사건의 SPY/TLT 정규화된 분봉 종가·가용 시각·원본 해시 |
| `consensus_json` | `ConsensusVintage` 배열 | 과거 사건과 대상 사건 모두 발표 전에 보존한 컨센서스 |
| `target_quotes_json` | `ThresholdQuote` 배열 또는 전체 `kalshi-cpi-threshold-curve-v1` 보고서 | 대상 사건의 다중 임계값 원시 호가 항목·시각·해시; summary는 불가 |
| `authorization_record` | `cpi-serving-authorization-v1` 기록 | 보관·통계 분석·파생 결과 공개 범위의 증빙 참조·적용 자료·유효기간 |

CSV의 필수 열은 다음과 같다. 기존 수집기가 저장한 부가 열은 유지해도 된다.

- 최초 발표: `event_id,event_ticker,release_at,actual_mom_first,source_url,raw_hash`.
- 분봉: `asset_id,price_at,available_at,open,high,low,close,volume,extended_hours,raw_hash`.
- 컨센서스 JSON: `event_id,expected_mom,available_at,source,raw_hash`.
- 정규화 호가 JSON: `event_id,market_ticker,threshold,probability_above,observed_at,available_at,spread,raw_hash`.

컨센서스와 호가의 `event_id`는 대응하는 `event_ticker`, 예를 들어 `KXCPI-26AUG`다.
수치 단위는 퍼센트포인트다. `0.3`은 `0.3%`이며 `0.003`이 아니다.
기존 고정 `0.3%` 이진 outcome으로 사건을 탈락시키지 않는다.

## 실행 순서

```bash
# 외부 API·키 없이 합성 원본 → 서비스 스냅샷 경로 확인
make PYTHON=.venv/bin/python serving-demo

# 파일 위치·존재·이용 기록만 확인. 금융 파일 본문은 읽지 않는다.
make PYTHON=.venv/bin/python serving-audit

# 이용 범위와 실제 자료를 확인한 뒤 변환
make PYTHON=.venv/bin/python serving-build SERVING_MANIFEST=data/clean/cpi-serving-manifest.json
```

`serving-audit`는 누락이 있어도 감사 수행이 성공하면 종료 코드 0이다.
입력 준비 완료를 뜻하지 않는다. 정식 build가 차단되면 종료 코드 2다.
출력 JSON의 `status`, `blocker_codes`, `snapshot`을 확인한다.
`inputs_present`는 파일과 이용 기록의 존재만 확인한 상태이며 내용 검증 전이다.
`snapshot_built`여도 시나리오 표본이 부족하면 API에서 전체 계산을 보류한다.

연결 설정 예시이며, 아래 대상 사건의 실제 자료 확보를 의미하지 않는다.
경로는 설정 파일의 디렉터리를 기준으로 해석하며 절대 경로도 가능하다.

```json
{
  "schema_version": "cpi-serving-manifest-v1",
  "source_kind": "licensed_historical",
  "source_reference": "이용 범위를 확인한 자료 묶음의 내부 참조",
  "target_event_id": "KXCPI-26AUG",
  "as_of": "2026-09-11T12:25:00Z",
  "release_at": "2026-09-11T12:30:00Z",
  "label_timing_policy": "official_release_timestamp_proxy",
  "release_csv": "releases/release_vintage.csv",
  "asset_bar_csv": "prices/asset_minute_bars.csv",
  "consensus_json": "consensus/consensus_vintages.json",
  "target_quotes_json": "quotes/full_curve_report.json",
  "authorization_record": "usage/verified_scope.json"
}
```

이용 기록은 `reference`, `data_scopes`, `uses`, 선택적 `valid_until`을 갖는다.
확인 대상 자료 범위는 `cpi_releases,asset_prices,consensus,event_probabilities`,
사용 범위는 `storage,statistical_analysis,derived_publication`이다.
**이 필드에 값을 쓰거나 저장소 변수를 설정하는 행위가 공급자 허가를 만들지는 않는다.**
증빙을 확인한 사람이 그 범위를 기록하는 형식 검사다. 없는 기록·불완전한 범위·만료된 기록은
금융 파일 본문을 읽기 전에 차단한다. [기존 이용 범위 점검](troubleshooting/kalshi-data-use-authorization.md)을 따른다.

## 시간과 계산 정의

- 각 과거 사건에 대해 SPY·TLT의 발표 전 1분, 발표 후 5분·30분 종가가 필요하다.
  수익률은 `end.close/start.close - 1`이다. 없는 가격은 보간하거나 이전 가격으로 채우지 않는다.
  기존 Alpaca 수집기는 분봉 시작 시각에 1분을 더해 종가·가용 시각을 정규화한다.
  이 변환기에는 정규화된 `price_at`을 주며 추가로 1분을 더하지 않는다.
- 과거 컨센서스는 그 사건의 발표 전 자료여야 한다. 자산 반응의 가용 시각은 대상 분석
  기준시각을 넘지 않아야 한다. 대상 사건·미래 사건은 과거 관측에 포함하지 않는다.
  중복 사건·컨센서스·같은 자산의 같은 분봉은 임의 선택 없이 오류 처리한다.
- 두 자산과 두 구간이 모두 완전한 사건만 사용한다. m30 하나가 빠지면 m5에서도 사건을 제외한다.
  엄격한 교집합의 표본 손실을 사건별 커버리지 보고서에 기록한다.
- `official_release_timestamp_proxy`는 최초 발표값의 가용 시각을 공식 발표 시각으로
  대리한다는 명시적 가정이다. 실제 수신 레이턴시를 측정한 것이 아니다.
  기존 전체 호가 보고서의 candle end도 가용 시각의 대리값이다.
  따라서 실제 수신 지연이 0이거나 정보 누수가 완전히 제거됐다고 주장할 수 없다.
- 기존 계약 정의·0.1 보고 격자·호가 시효·스프레드·PAVA 보정·확률 분포 검증을 재사용한다.
  형식 검사 통과는 원본 값의 진실성이나 예측 유효성의 증명이 아니다.
- 같은 사건의 SPY·TLT 수익률에 사용자 비중을 먼저 적용한 후 시나리오 확률로 분포를 혼합한다.
  양의 확률 시나리오별 최소 10건은 표시 기준이며 통계적 충분성의 보장이 아니다.

내용 해시별로 `snapshots/<hash>/scenario_dataset.json`, `lineage/<hash>/report.json`,
`readiness/<hash>/report.json`을 분리 보관한다. 같은 내용은 덮어쓰지 않는다.
입력 바이트 해시·정규화된 설정 해시·이용 기록 해시·시간 대리 규칙·제외 이유를 남긴다.
실제 원본과 결과는 Git에서 제외된 디렉터리에 두며 CI에서는 합성 변환만 실행한다.

## API와 화면 연결

API 프로세스의 `SHOCKGRAPH_SCENARIO_DATASET`에는 build의 `snapshot`,
`SHOCKGRAPH_CPI_READINESS`에는 같은 build의 `readiness_report` 경로를 설정하고 재시작한다.
PowerShell에서는 `$env:변수명="경로"`를 사용한다. 두 변수는 API 키가 아닌 파일 경로다.
합성 스냅샷은 actual로 적재할 수 없으며 데모는 계속 `source=demo`로 명시한다.

`GET /v1/data-readiness/cpi`는 적재 상태·공개 가능한 누락 항목·점검 시각·사건 수를 제공한다.
파일 경로·이용 기록 본문·가격 원본 행은 공개하지 않는다. 감사 보고서를 명시적으로 설정하면
실제 스냅샷 파일 해시와 보고서 해시가 일치해야 한다. 보고서가 손상됐거나 합성 출처이거나
해시가 다르면 실제 계산을 닫는다. `snapshot_built` 보고서만 있고 스냅샷이 없으면 `pending`이다.
포트폴리오 API의 `pending` 응답에도 누락 항목을 넣어 실제 화면에 표시한다.
이전 방식의 감사 보고서 없는 실제 스냅샷 적재는 호환을 유지하되 운영에서는 둘을 함께 설정한다.

이번 조회는 역사적 분석 스냅샷이며 최신 CPI 일정을 자동 조회하거나 대상을 갱신하지 않는다.
자동 갱신·장기 원본 저장은 이용 범위를 확인한 뒤 이어갈 작업이다.

## 현재 자료 상태와 다음 행동

현재 작업구의 `data`, `artifacts` 및 첨부 ZIP 12개의 파일 목록을 확인했다.
연결 가능한 실제 사건 CSV·과거 컨센서스·이용 기록을 찾지 못했다. 사용자의 집에 있는
로컬 파일까지 없다는 뜻은 아니다. SIP 5051개 분봉·BLS 53개 사건은 기존 집계의 수집 기록이며,
현재 사건별 원본을 복원할 수 있는 파일이 아니다.

Actions run `36874806023`, artifact `11167299993`에는 집계 JSON 6개만 있다.
이번 확인 시 미만료였고 만료 시각은 `2026-10-15T14:16:29Z`다. 서비스에 필요한 원본 CSV는 없다.
우선 이용 범위를 확인한 기존 release/price 원본을 찾아 복구하고, 당시 컨센서스와 대상 전체
호가가 보존돼 있는지 점검한다. 과거 컨센서스가 없다면 actual로 대신 채울 수 없다.
검증 가능한 다른 출처를 확인하거나 앞으로의 발표 전 자료를 보관해야 한다.
실제 수치를 보여주는 완료 조건은 이 입력들이 검증을 통과하고 API에 적재되는 것이다.

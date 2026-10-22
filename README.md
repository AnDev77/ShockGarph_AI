# ShockGraph AI

[진행 기록](docs/progress.md) · [트러블슈팅](docs/troubleshooting.md)

TLT·SPY 가격의 첫 기술 공급원은 Alpaca SIP 일봉이다. 키가 실행 환경에 있다면
`make collect-alpaca PRICE_END=2026-10-20 PYTHON=.venv/bin/python`으로 미국
수신일 이전의 가격 전체 이력을 원본·조정 방식별로 보관할 수 있다.
실행 방법과 비공개 출력은 [수집기 안내](apps/collector/README.md), 공급원
판정과 미검증 권리는 [자료 게이트](docs/data-source-gate-b.md)를 따른다.

공개 재무부 10년물 XML의 비공개 원본 수집은 [수집기 안내](apps/collector/README.md)를
따른다. 금리 수집에는 API 키가 필요하지 않다. 보관 원본을 검증해
`UST10Y_PAR` 날짜별 특징량으로 읽는 비공개 모델 B 경로도 있다. TLT·SPY 가격은 별도의 시점별
공급원·표시 권리 확인이 필요하며, 공개 금리만으로 ETF 예측 성능을 판정하지 않는다.

ShockGraph AI는 SPY·TLT 각각의 가격 변화와 관측 위험을 설명하고,
입력 비중의 기간 총변동률을 선택적으로 계산한다. 별도 연구에서는 당시
가격·금리·변동성 정보로 ETF의 향후 위험 범위를 검증한다.
거시 발표의 당시 기대와 실제 결과를 별도로 설명하는 제품을 목표로 한다. 첫 정답은
TLT의 미래 5·20거래일 실현 변동성이다. 가격 기준선 A와 전통 시장 정보 모델 B를
같은 날짜에서 비교하고, 충분한 독립 표본이 있으면 머신러닝의 추가 가치를 검토한다.
Kalshi의 특정 계약 확률은 계약 참가자가 그 시각에 반영한 기대를 출처와 함께
보여주는 맥락 자료이며 위험 예측의 필수 입력이 아니다. SPY·TLT는 첫 제품의
독립 종목 카드 대상이고, QQQ·XLE는 자료와 수요를 확인한 뒤 확장한다. 기존 CPI/Kalshi 계약 적중률 감사와
확률 추가 C 입력 경로는 선택적 연구 이력으로 보존한다. 전통 정보 모델 B의
기준선 A 대비 성과와 A 자체의 오차·사용성을 따로 평가한다. 수치가 신뢰할 수
없을 때는 발표 전 기대·최초 발표 결과·
TLT/금리 관측을 시점별로 자동 결합한 리포트가 수동 조사보다 나은지 따로
시험한다. 반복 사용과 토론 수요가 확인되어야 비동기
의견을 검토하고, 후속으로 종목 보유 인증 채팅방을 검토한다.
거래 실행과 개인화된 매수·매도 권유는 제공하지 않는다.

**2026-10-21 목표 및 현재 단계:** 기존 Kalshi CPI 계약 적중률 코드는 연구 이력이다.
보관 가격 기준선에 전통 지표·단일 계약 확률을 발표 전 시각으로 연결하고
결측·지연 날짜를 세는 입력 패널은 합성 자료로 검증했지만, 확률 결합 학습과
실자료 성능은 없다. 이 선택적 연구 경로는 첫 제품을 막는 필수 작업이 아니다.
일별 위험은 이용 가능 시각을 검증하는 가격 계약, 단일 ETF·복수 ETF의 합성 데이터 기준선,
2026년 Nasdaq 일정과 비공개 TLT CSV의 원본 보존·품질 검사 경로,
보관된 전체 수정가격 스냅샷을 예측 당시 시각으로 선택하는 합성 기준선과
보관 파일을 입력으로 받는 비공개 5·20일 시간순 평가 보고 경로를 구현했다.
보관 가격과 이용 가능 시각이 적힌 전통 지표를 결합하는 A/B 비교기에
가격 전용 Ridge 비교군과 GARCH(1,1) 통계 기준선을 추가해 합성 자료로
검증했다. 현재 TLT 수정종가 한 벌에 대한 비공개 탐색 그래프도 만들었다.
단일 종목의 과거 상태 계산기는 구현했으나 실제 SPY 가격 파일이 없어 SPY
결과와 웹 화면·채팅은 아직 없다. 종목별 화면과 공개 채팅을 예측 모델
승인과 분리해 진행하는 범위는 [제품 화면](docs/product-ui-direction.md)에 기록했다.
실제 시점별 가격·금리 공통 표본의 성능은 아직 없다.
공급 계약이 확인된 실가격 파일·수정가격의 과거 버전 증거·승인된 예측 모델·웹 화면·주주 인증과 채팅은 아직 없다.
현재 내려받은 실제 TLT 수정종가 한 벌로 **비공개 탐색 평가**는 수행했다.
가격 이력만 학습한 Ridge와 GARCH 후보 모두 5·20일 MAE가 EWMA보다 커서 승인하지 않았다.
이 실험으로 거시 확률의 예측 가치를 부정하거나 긍정할 수는 없다.
이는 과거 예측 당시의 가격 버전을 증명하지 않으므로 엄격한 **예측 실증은 HOLD**다.
[데이터 가능성 판정](docs/data-source-gate-b.md#2026-10-20-예측-실증-가능성-판정)에서
과거 버전·이용권 부재, 이미 관찰한 2026년 구간의 짧은 20일 홀드아웃, 원시 종가와 기업행동을
시점별로 재구성하는 대안을 구분했다. 합성 시험 수치를 제품 성능으로 사용하지 않는다.
새 범위는 [프로젝트 명세](shockgraph-ai-project-spec.md),
[현재 상태가 표시된 프로젝트 흐름도](docs/project-flow.md),
[일별 위험 방법론](docs/daily-risk-methodology.md),
[TLT 변동성 모델 설계](docs/tlt-volatility-model-design.md),
[제품 목표와 예측 성과별 커뮤니티 경로](docs/product-goal-and-fallback.md),
[연준 연구를 검토한 포트폴리오 위험 방법론](docs/portfolio-risk-methodology.md),
[주주 인증 채팅 후속 설계](docs/shareholder-community-roadmap.md)에 기록했다.

## 전통 지표 A/B 비공개 비교

`make risk-evaluate`에서 쓰는 **보관 전체 수정가격 스냅샷 manifest**와
별도의 전통 지표 CSV가 필요하다. 지표 파일은 저장소 밖 또는 무시된 비공개
경로에 두고 `name,source,observed_at,available_at,captured_at,value` 열을 사용한다.
세 시각은 UTC이며 `available_at`은 공급원에서 해당 버전을 API로 받을 수 있게
된 시각, `captured_at`은 **우리 쪽에서 실제 응답을 받은 시각**이다. 둘 중 늦은
수집 시각부터 해당 행을 사용한다. 관측 날짜만 제공하는 `DGS10`에 근거 없는
일중 관측 시각을 만들어 쓰지 않는다. CSV에 수집 시각을 적는 것만으로 실제
수집 사실이 인증되지는 않는다. 원본 응답·수신 로그·시계 동기화와 이용권 확인은
별도 과제이며 보고서는 `indicator_capture_times_verified=false`를 유지한다.
수집 시각이 없는 예전 5열 파일은 `--allow-unverified-indicators`를 명시해야만
합성·탐색 연구에 사용할 수 있다.

```bash
make risk-compare SNAPSHOT_MANIFEST=/private/manifest.json \
  INDICATOR_HISTORY=/private/indicators.csv PYTHON=.venv/bin/python
# 실제로 받은 재무부 원본이 있다면 날짜별 10년물을 비교 입력으로 사용한다.
make risk-compare SNAPSHOT_MANIFEST=/private/manifest.json \
  TREASURY_RAW_ROOT=data/raw PYTHON=.venv/bin/python
# TLT 단일 수정종가 이력과 보관 금리의 날짜·수신 시각 커버리지다.
make treasury-coverage PRICE_HISTORY=artifacts/tlt-adjusted-history-private.csv \
  TREASURY_RAW_ROOT=data/raw PYTHON=.venv/bin/python
# 기본 지표 DGS10 외 복수 지표를 시험할 때는 다음 CLI에서 --indicator를 반복한다.
.venv/bin/python scripts/evaluate_traditional_holdout.py \
  --manifest /private/manifest.json --indicators /private/indicators.csv \
  --indicator DGS10 --indicator VIXCLS --output artifacts/private-ab.json
# 주간 연은 지수 후보는 이름별로 경과시간을 따로 제한한다.
.venv/bin/python scripts/evaluate_traditional_holdout.py \
  --manifest /private/manifest.json --indicators /private/indicators.csv \
  --indicator DGS10 --indicator NFCI_RISK \
  --indicator-age-hours DGS10=48 --indicator-age-hours NFCI_RISK=240 \
  --output artifacts/private-ab-fed-context.json
```

재무부 원본에는 관측 날짜만 있어 일중 발표 시각을 채우지 않는다. 보관 원본의
UTC 수신 시각 이전 예측에서는 해당 금리를 제외하고, 날짜 시작을 신선도 계산의
보수적 기준으로 삼는다. `treasury-coverage`는 날짜가 겹치는 수와 수신 뒤의
가격 세션을 설명하는 보고이며 모델 정확도 결과가 아니다. 이 실행 환경에서는
2026-10-22 공식 피드의 실제 월별 응답 2건을 수신했다. 당시 TLT 파일은
2026-10-16에 끝나 수신 **이후** 가격 세션이 0건이다. 금리 원본 보관소가 비어 있으면
보고 명령은 입력 오류로 끝난다. 현재 TLT 수정종가 파일에는 당시의 과거 버전이
없어 공통 자료가 생겨도 그것만으로 공개 성능을 주장할 수 없다.

`NFCI_RISK`는 CSV에 입력할 **연구용 시리즈 이름 예시**이며 실제 주간 지수를
자동 수집하지 않는다. 위 48·240시간은 사용법을 보이는 설정 예시다. 각 지표의
정확한 관측 기간·게시 시각·휴장일·과거 수정 가능성을 확인한 뒤, 최종 평가 전에
신선도 상한을 고정해야 한다. 일별 금리와 주간 위험지수를 함께 요구하면 하나라도
빠진 날짜는 B와 B0의 공통 비교에서 제외된다. 제외 이유와 해당 지표명은 비공개
보고의 `coverage.indicator_exclusions`로 확인한다. 기본 경과시간은 기존 120시간이다.

비교기는 A의 최근 변동성·EWMA와 일별 수익률 GARCH(1,1), 가격만 쓴
Ridge(B0), 가격·지표 Ridge(B1)를 같은 홀드아웃 날짜에서 채점한다.
`B1−B0`는 회귀 구조와 날짜를 같게 두고 지표 입력만 추가한 차이다.
B0·B1은 훈련 기간에서만 표준화한 고정 패널티 Ridge이고
훈련 정답은 **홀드아웃 시작 전에 받은 가격 스냅샷**에서, 시험 정답은 평가 시점의
스냅샷에서 만든다. 기본 학습 최소 100행과 기간별 정답의 비중첩 구간 최소 2개가
없으면 점수를 숨긴다. GARCH는 홀드아웃 이전의 일별 수익률이 기본 100개
미만이거나 추정이 수렴하지 않으면 해당 점수만 보류한다. 결과는 입력 파일 해시·결측·표본 수·MAE·QLIKE·불확실성
구간을 담는 **비공개 연구 보고**이며 `public_performance_allowed=false`다.
현재 로더의 거래소 달력은 검토한 2024~2026년 일정에 한정된다. 2025년 1월 9일
임시 휴장도 반영했으나 과거 수정가격 파일·이용권과 새 독립 평가 기간은 여전히 필요하다.
달력 변경과 다년 합성 비교의 검증은 [다년 거래일 리뷰](docs/reviews/multiyear-nasdaq-risk-calendar-review.md)에 기록했다.

[FRED의 DGS10](https://fred.stlouisfed.org/series/DGS10)과
[VIXCLS](https://fred.stlouisfed.org/series/VIXCLS)는 후보 지표지만, FRED의
[과거 버전 API](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)는
날짜별 빈티지를 제공할 뿐 일중 게시 시각이나 가격 파일의 과거 실제 캡처를
자동 증명하지 않는다. 특히 VIX는 원 공급원 CBOE의 저작권·표시 조건을
별도로 확인해야 한다. 자료의 시점과 사용 권리, 새 독립 시험 기간이 없으면
실증 성과를 주장하지 않는다.

[시카고 연은 NFCI 위험 하위지수](https://www.chicagofed.org/research/data/nfci/about)는
금융시장의 변동성과 자금조달 위험을 포함하는 **주간 시장 상태 지표**다.
[세인트루이스 연은 STLFSI4](https://fred.stlouisfed.org/series/STLFSI4)도
주간 금융시장 스트레스 지표이며 개별 ETF의 향후 위험 정답은 아니다. 둘 다
후보 입력으로만 다루고, 가격만 쓴 B0와 같은 날짜에서 추가 효과를 검증한다.
지표 원본·과거 게시 시각과 공개 재사용 조건은 아직 확보하지 않았다.

입력·평가 계약과 합성 시험 결과는
[전통 지표 A/B 홀드아웃 리뷰](docs/reviews/traditional-risk-ab-holdout-review.md)에 기록했다.

## 일별 위험 기준선 실행

`make risk-demo`는 합성 가격과 합성 평일 달력만 사용해 TLT 형식의 5·20거래일
최근 변동성/EWMA 기준선을 평가한다. 출력의 `DEMO` 수치는 실제 TLT 성과가 아니다.
정답에는 미래 가격의 `available_at`이 지나야 접근하며, 명시된 세션이 빠지면 계산을
거부한다. 실제 공급원과 거래소 달력의 권리·게시 지연을 확인하기 전에는 제품 수치를
제공하지 않는다. 다자산 공동 수익률 기준선은 `make portfolio-demo`로 별도 시험하며
실제 투자 성과가 아니다. 구현 범위는 [15~16일차 리뷰](docs/reviews/day-15-16-review.md)와
[17~18일차 리뷰](docs/reviews/day-17-18-review.md)를 따른다.

## 종목별 과거 상태와 선택적 총변동률

SPY 또는 TLT의 `session_date,adjusted_close` CSV를 **각각** 입력해 최근
5·20·60개 입력 행의 가격 변화, 최근 관측 변동성의 과거 이력 내 위치,
기간 내 최대 하락 폭을 JSON으로 계산한다. 서로 다른 종목의 입력은 이
단계에서 필요하지 않다.

```bash
python scripts/analyze_asset_history.py --input /private/spy.csv \
  --symbol SPY --source "SPY 공급원·수신일" --window 60 \
  --output artifacts/private-spy-history.json
```

두 종목 요약의 시작·종료 날짜가 같을 때만 입력 비중의 총변동률을 별도
계산한다. 초기 비중으로 기간 내 재조정 없이 보유한 경우이며, 종목별 위험
점수를 섞거나 미래 성과를 예측하지 않는다. 출력은 비공개 과거 분석이고
`public_display_allowed=false`다. SPY 이력·외부 표시 권리와 전체 거래소
세션 대조가 남았다. [단일 종목 우선 리뷰](docs/reviews/asset-first-market-overview-review.md)를 참조한다.

## 비공개 TLT 가격 입력 점검

사용 권한이 확인된 CSV에 `session_date,observed_at,available_at,close,adjusted_close,volume`
열을 넣는다. 각 행은 2024~2026년 Nasdaq 정규장 세션 하나를 나타내며 `observed_at`은 해당
정규장 종가의 UTC 시각, `available_at`은 **그 수정가격 버전이 최초로 사용 가능했던
UTC 시각**이다. `volume`은 비울 수 있다. 파일을 받은 원래 UTC 시각을 `--captured-at`에
넣고, 원본을 공개 저장소 밖의 `data/raw/`에 보존한다.

```bash
python scripts/import_daily_prices.py --prices /private/tlt.csv --source licensed-provider \
  --captured-at 2026-10-19T22:00:00Z --start 2026-01-02 --end 2026-10-19
```

출력은 원본 체크섬, 휴장일을 제외한 예상 거래일 대비 누락·중복, 정규장 종가 시각,
종가 60분 뒤 예측 기준 시각보다 늦은 버전을 보여준다. `--prediction-delay-minutes`로
기준 시각을 명시적으로 바꿀 수 있다. 같은 파일과 `captured-at`으로 재실행하면
불변 원본을 중복 저장하지 않는다. 현재 달력은 검토한 2024~2026년 거래일이며
이후 공지된 추가 예외 일정은 별도 확인해야 한다. `structurally_ready`는 기계적
입력 점검 결과이며 공급 계약·과거 버전 진위를 승인하거나 실자료 성능을 산출하지 않는다.
자세한 제한과 다음 검증은 [19~20일차 리뷰](docs/reviews/day-19-20-review.md)에 적었다.

### 과거 수정가격 스냅샷

배당이나 분할로 과거 `adjusted_close`가 달라질 때는 당시 보관한 **전체 가격 이력
파일을 날짜별로 별도 보존**해야 한다. 한 파일에 동일 세션을 중복 입력하지 않는다.
각 파일을 수신 시각의 `--captured-at`과 그 파일의 마지막 세션을 `--end`로 지정하고
`--full-snapshot`으로 검사할 수 있다.

```bash
python scripts/import_daily_prices.py --prices /private/tlt-snapshot.csv \
  --source licensed-provider --captured-at 2026-04-07T20:10:00Z \
  --start 2026-03-30 --end 2026-04-07 --prediction-delay-minutes 10 --full-snapshot
```

`full_snapshot`에서는 과거 행의 수정본이 원래 거래일 예측보다 늦게 나온 사실을
`late_sessions`에 남기되, 전체 스냅샷의 구조 검사에서 이를 오류로 취급하지 않는다.
실제 기준선 함수는 파일마다 `PriceSnapshot(captured_at=imported.captured_at,
prices=imported.prices)`를 만들고 `build_snapshot_forecasts`에 **캡처 순서대로**
전달한다. 각 예측은 그때까지 캡처됐고 해당일까지 완전한 최신 파일 **한 개**만
사용한다. 최종 평가의 정답은 별도 스냅샷으로 계산한다. 공급원의 실제 권리와
과거 수신·버전 증거가 없으면 이 기능 역시 합성 데이터 검증에만 사용한다.
[수정가격 스냅샷 리뷰](docs/reviews/price-vintage-asof-review.md)에 시점 규칙을 정리했다.

### 보관 파일의 시간순 평가

공개 저장소 밖에 `manifest.json`과 각 시점에 **실제로 보관한 전체 이력 CSV**를 둔다.
입력의 최소 형식은 다음과 같다. 실제 점수를 얻으려면 `start`부터 `end`까지
예측을 평가할 각 거래일마다 예측 시각 전에 받은 완전한 파일과 충분한
미래 정답 구간이 필요하다.

```json
{
  "schema_version": 1,
  "source": "licensed-provider",
  "start": "2026-01-05",
  "end": "2026-01-05",
  "holdout_start": "2026-01-05",
  "evaluation_at": "2026-01-05T21:10:00Z",
  "prediction_delay_minutes": 10,
  "snapshots": [
    {
      "path": "capture-2026-01-05.csv",
      "captured_at": "2026-01-05T21:05:00Z",
      "end": "2026-01-05"
    }
  ]
}
```

`path`는 manifest 파일이 있는 디렉터리를 기준으로 해석한다. 위 한 거래일 예시는
입력 형식을 보여줄 뿐 5·20일 성과를 낼 표본은 없다. `holdout_start`는 고정된
거래일이며 해당일의 정규장 종가와 `prediction_delay_minutes`를 합친 시각부터
비교한다. `evaluation_at`은 적어도 마지막 예측 시각 이후여야 한다.

```bash
python scripts/evaluate_snapshot_holdout.py --manifest /private/manifest.json \
  --raw-root data/raw --output artifacts/tlt-holdout.json
# 또는: make risk-evaluate SNAPSHOT_MANIFEST=/private/manifest.json
```

보고서에는 manifest·원본 해시, 예정 거래소 달력 버전, 기간별 입력 지문,
예측·정답 행 수와 비중첩 구간 수를 남긴다. 2개 비중첩 구간보다 적으면
`blocked`와 이유만 내고 점수를 숨긴다. 그 이상이어도
`evaluated_research_only`의 MAE·QLIKE·짝지은 블록 재표집 구간은 **비공개 연구 결과**다.
원본 수신 시각의 진위, 공급원 이용 권리, 임시 휴장과 배당·분할 조정의 정의는
자동 확인되지 않으므로 실제 TLT 성과나 공개 서비스 승인으로 해석할 수 없다.
[보관 스냅샷 홀드아웃 리뷰](docs/reviews/snapshot-holdout-review.md)에 검증 범위를 기록했다.

### 현재 수정종가 한 벌로 하는 탐색 평가

비공개 CSV에 `session_date,adjusted_close` 두 열을 날짜순으로 적는다.
예를 들어 직접 내려받은 TLT 수정종가를 `artifacts/tlt-private.csv`에 둔 뒤
다음 명령으로 두 기준선의 5·20일 미래 변동성 오차를 계산한다.

```bash
python scripts/evaluate_exploratory_history.py --input artifacts/tlt-private.csv \
  --source "가격 공급원과 내려받은 날짜" --holdout-start 2024-01-02 \
  --output artifacts/tlt-private-evaluation.json
# 또는: make risk-explore PRICE_HISTORY=artifacts/tlt-private.csv \
#   PRICE_SOURCE=licensed-provider HOLDOUT_START=2024-01-02
```

입력 파일과 결과 JSON은 `.gitignore`에 포함된 비공개 위치에 보관한다. 현재 내려받은
한 벌의 수정종가에는 과거 날짜마다 언제 그 값이 공개·정정됐는지 기록되지 않는다.
평가기는 날짜가 늘어나는 순서와 숫자 형식만 검사하고 **거래소 달력 전체와 과거
수정가격 버전은 검증하지 않는다.** 결과는 과거 5·20개 **입력 행**으로 미래 같은
수의 행을 예측한 탐색 결과이며, 상품 성능이나 AI 모델의 개선 근거가 아니다.
같은 비공개 자료에서 비교 모델을 실행하려면 `--compare-model`을 추가한다.
이 모델은 과거 1·5·20행의 변동성을 입력으로 쓰고, **시험 시작일 전에 미래 결과까지
확정된 행**으로 한 번 학습한다. 시험 기간 중 모델을 재학습하거나 시험 성능으로
설정을 고르지 않는다. 최근 변동성·EWMA와 같은 시작 날짜·미래 정답에서 오차를
비교한다.

```bash
python scripts/evaluate_exploratory_history.py --input artifacts/tlt-private.csv \
  --source "가격 공급원과 내려받은 날짜" --holdout-start 2024-01-02 \
  --compare-model --output artifacts/tlt-private-model.json
# 또는: make risk-explore PRICE_HISTORY=artifacts/tlt-private.csv \
#   PRICE_SOURCE=licensed-provider HOLDOUT_START=2024-01-02 COMPARE_MODEL=1
```

실제 가격의 탐색 비교와 계산 검증은 [기준선 리뷰](docs/reviews/tlt-exploratory-baseline-review.md),
[첫 모델 비교 리뷰](docs/reviews/tlt-price-only-model-review.md)에 기록했다.
후속 GARCH(1,1)·HAR-RV와 시장 변수의 실험 순서는
[논문 기반 TLT 모델 설계](docs/tlt-volatility-model-design.md)에 정리했다.

#### 실제 가격 한 벌의 GARCH 탐색 시각화

시각화 추가 의존성은 `python -m pip install -e '.[dev,viz]'`로 설치한다.
기존 탐색 평가와 같은 두 열의 비공개 CSV로 그림과 상세 JSON을 생성한다.

```bash
python scripts/plot_exploratory_garch.py --input /private/tlt-adjusted-history.csv \
  --source "가격 공급원과 내려받은 날짜" --holdout-start 2024-01-02 \
  --output-dir /private/exploratory-visual
```

그림의 위 두 패널은 5·20일 미래 일별 변동성의 실제값·EWMA·GARCH 예측을
보기 쉽도록 20개 평가 시점씩 평활화한다. 아래 막대는 같은 평가일의 **원래
값**으로 계산한 최근 변동성·EWMA·Ridge·GARCH MAE다. 실제 한 벌의 과거
수정종가만 사용했으므로 예측 당시 가격 버전이나 새 독립 시험을 확인한 성능은
아니다. [GARCH 탐색 시각화 리뷰](docs/reviews/tlt-exploratory-garch-visual-review.md)에
표본·오차·지표별 차이와 해석 제한을 기록했다.

## 기존 이벤트 연구 구현 상태

1~12일차 작업에서 데이터 계약, 발표 단위 기준 모델 비교와 Kalshi CPI 실데이터
감사까지 구현했다.

- API, 웹, 수집기, 분석 패키지, 인프라의 저장소 구조
- Kalshi API 계약 검증용 고정 응답 자료
- 응답 정규화와 원본 해시 계산
- 이벤트 단위 분할과 시각 기반 미래 정보 누수 방지
- 읽기 전용 공개 API의 기술적 가용성 확인 스크립트
- 진행 가능·범위 축소·보류 판단 문서
- UTC를 강제하는 이벤트, 시장 관측, 호가창 데이터 계약
- 원본 추적 제약조건을 갖춘 PostgreSQL 수집 스키마
- 재시도 횟수 제한과 커서 페이지네이션을 갖춘 GET 전용 공개 수집기
- 내용 기반 불변 원본 저장
- S3 호환 객체 키·저장 프로토콜과 불변 로컬 어댑터
- 큐·저장소 인터페이스와 원본 정규화 작업의 멱등 키
- TimescaleDB용 자산 가격·특징량 스키마와 트랜잭션 아웃박스 스키마
- UTC에서 미국·한국 거래소 현지 날짜로의 변환과 기준시점 정렬
- 이벤트별 시간순 확률 보정 데이터 분할
- 시장확률을 그대로 사용하는 기준 모델과 Brier 점수·표본 수·불확실성 계산
- 모델 산출물·체크섬·버전·평가 지표 등록 계약

- 발표 전 확률·기대·가격의 시점 검증과 이벤트별 커버리지·제외 사유
- 과거 수익률 분포와 이벤트 확률 가중 분포의 순차 학습·평가
- 자산·포트폴리오 CRPS, 상승확률 Brier, 하방 분위수 손실, 발표 단위 대응 재표집
- 정규화 입력과 결과 체크섬을 포함한 재현 리포트 CLI 및 합성 실행 예제
- Kalshi 공식 호환 운영 URL을 이용한 현재·과거 KXCPI 1분 캔들 수집
- 결과 확정 `T0.3` 55개 사건의 유동성·신선도 감사와 29개 유효 확률 확인
- 24개 동일 사건에서 원시 시장확률과 누적 과거비율의 시간순 Brier 비교
- 논문용 사건 자료 CSV와 계보 메타데이터의 내용 해시 기반 내보내기

Kalshi 정산확률의 첫 실데이터 기준 비교는 완료했지만 SPY·TLT·GLD 가격과 결합한
자산 반응 모델, 웹 화면과 실제 데이터베이스 연결은 아직 없다.

현재 작업 결과는 [분석 개발 리뷰](docs/reviews/day-05-06-review.md),
재접속 후 상태는 [연동·재검증 기록](docs/reviews/analytics-sync-checkpoint.md), 목표 구조는
[아키텍처 문서](docs/architecture.md)에서 확인할 수 있다.

## 연구 이력과 제품 설계

- [이벤트 분석 파이프라인 학습 가이드](docs/study-guide-analytics.md): 실행 방법, 시간 누수, 경험적 분포, CRPS, 지속 학습과의 연결
- [이번 CPI·ETF 커버리지 점검](docs/cpi-coverage-review.md): CPI 확률 실데이터와 ETF 연결 조건
- [논문 연구 패키지](docs/paper/README.md): 연구 프로토콜, 데이터 사전, 분석 계획, 논문 구성과 선행연구
- [데이터 파이프라인·확률 평가 학습 가이드](docs/study-guide-day-03-04.md): 6회 학습 순서, 코드 읽기, 실습, 금융 예제, 구현 한계
- [제품·Chakra UI 화면 설계](docs/product-ui-direction.md): 일별 위험 홈, 근거·시나리오, 후속 종목방의 화면 계약

설정 파일의 자산 목록은 분석 후보이며 학습 완료 목록이 아니다.
새 위험 분석 API와 Next.js·Chakra UI 화면은 구현 예정이다.

## 로컬 실행

Python 3.12가 필요하다. 아래는 Windows 기준 명령어다.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```

macOS와 Linux에서는 `.venv/bin/python`을 사용한다.

가상환경의 Python으로 합성 이벤트 분석을 실행할 수 있다.

```bash
python scripts/run_event_research.py --input data/fixtures/analytics/synthetic_cpi.json --min-train 4
```

결과는 `artifacts/event-research/`에 저장되며 합성 결과는 금융 성능 근거가 아니다.

## 저장소 구성

- `apps/api`: 2주차 구현 예정인 FastAPI 영역
- `apps/web`: 3주차 구현 예정인 Next.js 영역
- `apps/collector`: 읽기 전용 수집 영역
- `packages/domain`: 금융 데이터·포트폴리오 계약
- `packages/data_pipeline`: 원본 계약, 객체 저장, 멱등 정규화, 계보 추적, 거래시각 정렬, 누수 방지
- `packages/calibration`: 이벤트별 데이터셋과 시장확률 기준 모델·Brier 평가
- `packages/risk_engine`: 단일 ETF 및 공동 포트폴리오 합성 변동성 기준선·평가
- `packages/*`: 나머지 이벤트 연구 영역
- `docs/data-feasibility.md`: 1일차 데이터 가용성 검토와 범위 결정
- `docs/data-source-gate-b.md`: 미국 자산·환율·국내 자산 공급원 검토
- `docs/architecture.md`: 원본 우선 수집과 데이터·모델·서빙 계층의 목표 구조
- `data/fixtures`: 원본 응답 형태를 따른 소규모 고정 테스트 자료
- `docs/reviews`: 요청별 변경 구조와 사용자 점검표

## 작업 규칙

문서는 한글로 작성하고, 커밋 제목에는 일차 대신 주요 변경 내용을 적는다.
상세 규칙은 [AGENTS.md](AGENTS.md)를 따른다.

공개 읽기 전용 엔드포인트나 데모 환경만 사용한다.
비밀키, 계정 데이터, 주문·거래 실행은 MVP 범위 밖이다.

# 수집기 영역

수집기는 읽기 전용이어야 하며 멱등성, UTC 시각 정규화, SHA-256 해시를 포함한 불변 원본 보존을 지켜야 한다.

현재 `shockgraph_collector.client.KalshiPublicClient`는 다음을 제공한다.

- 승인된 운영·데모 기본 URL만 허용
- 공개 GET 경로만 허용
- 429 및 일시적인 5xx 응답에 대해 횟수를 제한한 재시도
- 동일 커서 반복을 방지하는 커서 페이지네이션
- 불변 원본 저장소에 직접 저장

## 미국 재무부 10년물 금리 원본

`make collect-treasury PYTHON=.venv/bin/python TREASURY_MONTH=202610`은
[재무부의 공개 XML 월별 피드](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed)를
GET으로 조회한다. API 키를 요구하지 않는 공개 요청 URL을 사용한다. 실제 HTTP
응답을 완전히 받은 직후 UTC 수집 시각을 찍고, XML 바이트와 SHA-256을
`data/raw/`의 불변 저장소에 보관한다. 같은 시각·응답·요청의 재실행은 중복
원본을 만들지 않는다. 이 명령은 파일을 공개하거나 재배포하지 않는다.

`UST10Y_PAR`의 원천 관측 **날짜**와 10년물 금리만 추출한다. 원본의 날짜는
일중 측정·발표 시각이 아니며, 수집 시각이 과거의 API 공개 시각을 증명하지도
않는다. `load_treasury_history`는 보관된 원본 XML과 해시를 다시 검사한 뒤
각 수신본의 날짜별 10년물 값을 `UST10Y_PAR`로 모델 B 입력에 연결한다.
`make treasury-coverage PRICE_HISTORY=/private/tlt.csv TREASURY_RAW_ROOT=data/raw`
명령으로 TLT 가격 날짜와 원본 수신 이후 세션의 개수를 확인할 수 있다.
이는 수익률 예측 성능이 아니다. 과거 금리 `DGS10` CSV와 같은 시리즈라고
표시하지 않는다. 가격 수정 이력과 이용·표시 권리, 독립 시험 표본은 별도로 필요하다.

2026-10-22에는 프록시의 SOCKS 의존성을 갖춘 환경에서 공식 수집 명령으로
2026-10 월별 XML을 실제로 두 번 수신했다. 관측일 14개를 포함하지만 오늘
수신한 이력이 과거 14개 거래일의 공개 시각을 입증하지는 않는다.

## Alpaca TLT·SPY 일별 가격 원본

`APCA_API_KEY_ID`와 `APCA_API_SECRET_KEY`를 실행 환경에 설정한 뒤
`make collect-alpaca PRICE_START=2024-01-02 PRICE_END=2026-10-20 \
PYTHON=.venv/bin/python`을 실행한다. 미국 수신일 이전의 `PRICE_END`만 받는다.
`feed=sip`의 `adjustment=raw`와 `adjustment=all` 두 전체 이력을 각 종목에
요청한다. 페이지마다 실제 수신 시각, 원본 JSON 바이트, SHA-256을
`data/raw/alpaca/`에 보관하며 인증 헤더·키는 보관하지 않는다.

정규화된 TLT·SPY 전체 스냅샷 CSV와 원본 해시 manifest는 Git 추적에서
제외된 `artifacts/alpaca-private/` 아래 남는다. 일별 응답의 `t`는 거래일을
표시하므로, 검토된 미국 주식 거래일 달력의 마감 시각을 관측 기간 끝으로
기록한다. 가격 버전의 이용 가능 시각은 추측하지 않고 실제 전체 응답을
받은 시각으로 설정한다. 같은 날의 조정종가가 나중에 수정되면 새 버전으로
보관하고 과거 예측에 소급하지 않는다. 과거 수정 이력과 외부 표시 권리는
여전히 검증되지 않았다.

수집 manifest가 남은 같은 비공개 환경에서
`make analyze-alpaca ALPACA_MANIFEST=artifacts/alpaca-private/captures/<파일>.json \
HOLDOUT_START=2026-01-02 PYTHON=.venv/bin/python`을 실행하면 TLT와 SPY의
현재 조정 이력에서 5·20일 가격 기준선을 각각 비교한다. GitHub Actions도
수집 직후 해당 분석을 실행하지만 원본 가격과 CSV는 Actions 아티팩트에
올리지 않아 작업이 끝나면 삭제된다. 이 결과는 예측 당시의 과거 가격
버전이나 외부 표시 권리를 증명하지 않는다.

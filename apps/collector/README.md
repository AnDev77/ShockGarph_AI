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

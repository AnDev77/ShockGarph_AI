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
않는다. 현재 수집 결과는 모델 B에 곧바로 넣지 않고, 과거 금리 `DGS10` CSV와
같은 시리즈라고 표시하지 않는다. 응답의 권리·과거 수정본·수신 로그와
SPY/TLT 가격 자료가 결합되어야 시점별 A/B 실증을 진행한다.

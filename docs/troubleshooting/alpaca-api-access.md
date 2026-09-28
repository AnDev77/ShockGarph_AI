# Alpaca 과거 ETF 분봉 API 접근 문제 기록

기록일: 2026-09-28. 대상: SPY·TLT·GLD의 CPI 발표 전후 과거 1분봉.

## 이 환경에서 확인한 사실

| 분류 | 관측 | 결론 |
|---|---|---|
| 인증정보 | `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY` 미설정 | 수집 스크립트가 실제 HTTP 요청 전에 중단된다. 유효한 계정 권한은 검사하지 못했다. |
| 네트워크 | `data.alpaca.markets` DNS 조회 실패(`gaierror`, temporary failure in name resolution) | 실행 환경에서 API 서버까지 도달하지 못했다. HTTP 401·403·422를 받은 것이 아니다. |
| 과거 SIP 권한 | 계정으로 실호출하지 못함 | 실패 원인을 SIP 유료 구독으로 단정할 수 없다. |
| 실제 자료 | ETF 분봉 0건 | API가 데이터를 제공하지 않는다는 증거가 아니라 수집 미수행 상태다. |

## 공식 API 계약과 수정 사항

- 과거 주식 분봉: `GET https://data.alpaca.markets/v2/stocks/bars`;
  `symbols=SPY,TLT,GLD`, `timeframe=1Min`, `feed=sip`, `adjustment=raw`.
- 구독 없이 과거 SIP를 조회하려면 요청 `end`가 조회 시각보다 최소 15분 이전이어야 한다.
  실시간 SIP는 별도 구독 대상이다. 코드 기본값을 `sip`로 바꾸고 최근 요청을 사전에 거부했다.
- 응답은 종목 우선·시각 순으로 정렬된다. 한 페이지에 세 종목이 모두 없어도
  `next_page_token`이 사라질 때까지 조회해야 한다.
- `start`, `end`는 API 설명상 포함 경계이며 1분봉 `t`는 봉 **시작**시각이다.
  응답 봉 종료시각을 가격시각으로 사용하고 사건창의 정확한 봉만 인정한다.

근거: https://docs.alpaca.markets/us/docs/market-data-faq ,
https://docs.alpaca.markets/us/reference/stockbars

## 계정과 네트워크가 가능한 환경에서 재현할 순서

1. 개인 연구 계정에서 발급한 키를 로컬 환경변수에만 설정한다. 키를 문서·명령 인수·Git에 넣지 않는다.
2. DNS/TLS 연결이 되는 환경에서 **이미 지난 CPI 발표** 한 건의 SPY·TLT·GLD를
   `feed=sip`, `end`가 최소 15분 전인 조건으로 GET한다. HTTP 상태와 종목별 봉 개수만 기록한다.
3. `401/403`: 키·계정·호스트 확인. `422`의 최근 SIP 권한 메시지: `end`와 현재시각 확인.
   `429`: 호출 간격과 재시도 확인. `200`에 빈 배열: 해당 장전 분봉에 체결이 없을 가능성 확인.
4. 한 건 성공 후 53개 표준 월간 발표를 수집하고 `coverage.json`의 결측 사유,
   `metadata.json`의 `common_events`, 원본 해시를 대조한다. 실데이터를 Git에 올리지 않는다.

현재 환경에서는 1~4번 중 계정 인증 이후의 실제 API 성공 여부를 확인하지 못했다.

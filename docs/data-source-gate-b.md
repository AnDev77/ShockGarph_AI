# 자산 가격·환율 공급원 2차 검토

결정일: 2026-09-22

## 결론

| 데이터 | 후보 | 판정 | MVP 사용 방식 |
|---|---|---|---|
| 공식 경제지표·환율 | FRED/ALFRED API | 진행 가능(GO) | API 키는 환경변수로 주입하고 공개·개정 및 기준 시점을 보존한다. |
| 미국 ETF 일봉 | Alpha Vantage | 범위 축소(REDUCE_SCOPE) | 개인 연구용 수집 후보로만 두고, 공개 저장소와 시연에는 고정 예제·파생 통계만 사용한다. |
| 미국 ETF 장전 분봉 | Alpaca Historical Bars | 조건부 진행(CONDITIONAL_GO) | 개인 연구용 키와 IEX/SIP 피드를 명시하고 원시 자료는 로컬에만 저장한다. |
| 한국 ETF·주식 | KRX Data Marketplace/Open API | 보류(BLOCKED) | 이용계약과 재배포 범위를 확인하기 전 실제 값 수집기를 추가하지 않는다. |

3~4일차의 공급원 중립 계약 위에 17~18일차에 Alpaca REST 어댑터를 추가했다.
SDK 의존성 없이 `httpx` GET만 사용하며 주문·계좌 엔드포인트는 구현하지 않는다.

### Alpaca: 조건부 진행

- 공식 Historical API는 주식의 과거 자료를 제공하며, 주식·ETF 1분 집계봉과 장전 자료를
  조회할 수 있다.
- 무료 피드는 IEX 단일 피드이고 SIP는 전체 미국 거래소 피드다. 가격·거래량 커버리지가
  다르므로 한 연구 실행에서 두 피드를 섞지 않는다.
- 공식 안내상 과거 자료는 7년 이상이어서 현재 CPI 표본의 2021년 이후 구간을 포함할 수 있다.
- API 키가 필요하며 현재 실행 환경에는 키가 없어 실데이터 수집은 0건이다.
- Alpaca는 시장자료 재배포를 허용하지 않는다고 안내하므로 원본과 분봉 CSV는 로컬 연구
  전용으로 두고 Git·공개 화면에 배포하지 않는다. 파생 결과 공개도 별도 확인한다.
- `source_start_at`은 공급원 봉 시작시각, `price_at`과 `available_at`은 1분을 더한
  봉 종료시각으로 저장한다. 이 구분이 발표 후 5분 수익률의 오프바이원 오류를 막는다.

공식 문서:

- https://docs.alpaca.markets/us/docs/historical-api
- https://docs.alpaca.markets/us/reference/stockbars
- https://docs.alpaca.markets/us/docs/market-data-faq
- https://alpaca.markets/data
- https://alpaca.markets/support/redistribute-alpaca-api

## 판단 근거

### FRED/ALFRED: 진행 가능

- 공식 API는 시계열 관측값 조회와 JSON 응답을 지원한다.
- 실시간 유효기간과 자료 공개·개정일을 제공하므로 개정된 경제지표를 현재 값으로 소급해
  사용하는 누수를 피할 수 있다.
- API 키가 필요하므로 키는 저장소에 넣지 않고 환경변수로만 주입한다.
- FRED는 경제지표·환율 경계로만 사용하며 ETF 체결가격 공급원으로 간주하지 않는다.

공식 문서:

- https://fred.stlouisfed.org/docs/api/fred/
- https://fred.stlouisfed.org/docs/api/fred/series_observations.html

### Alpha Vantage: 범위 축소

- 공식 문서는 전 세계 주식·ETF의 일별 시가·고가·저가·종가·거래량과 수정 일봉 엔드포인트를 제공한다.
- 수정 일봉은 유료 엔드포인트이며 API 키가 필요하다.
- 호출 권한과 원천값 재배포 권한은 동일하지 않으므로 공개 데이터셋으로 커밋하지 않는다.
- 공급 계약을 확인할 때까지 로컬 연구 수집 후보이며 자동 테스트는 고정 예제만 사용한다.

공식 문서:

- https://www.alphavantage.co/documentation/

### KRX Data Marketplace: 보류

- 공식 Marketplace는 Open API 이용 경로와 데이터 구입 절차를 제공한다.
- 공모전 공개 시연과 저장소 재배포가 허용되는지는 별도 이용계약 확인이 필요하다.
- 계약 확인 전에는 한국 자산 원천값을 수집·커밋하지 않는다.

공식 문서:

- https://data.krx.co.kr/contents/MMC/MAIN/main/index.cmd
- https://data.krx.co.kr/contents/MDC/COMS/client/view/register_step3.jsp

## 어댑터 도입 조건

- [ ] API·상품 이용약관에서 연구, 시연, 결과물 공개 범위를 확인했다.
- [ ] 원천값 저장 위치와 보존기간을 정했다.
- [ ] 원본 시각, 수집시각, 거래일의 의미를 매핑했다.
- [ ] 수정주가 산식과 기업행동 처리 기준을 정했다.
- [ ] 거래소 휴장일 달력의 출처와 갱신 방식을 정했다.
- [ ] 요청 제한, 재시도, 체크섬, 중복 저장 테스트를 추가했다.
- [ ] IEX와 SIP 중 사용할 피드를 고정하고 전 표본에서 동일하게 사용한다.
- [ ] 장전 분봉의 결측률과 세 ETF 공통 사건 수를 확인했다.

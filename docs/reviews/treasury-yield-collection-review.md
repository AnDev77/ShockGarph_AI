# 공개 미국 국채금리 원본 수집 리뷰

작성일: 2026-10-22. 직전 작업은 사용자가 작성한 지표 CSV의 수집 시각을
게이트로 검사했다. 이번에는 API 키 없이 실제 응답을 받을 수 있는 재무부
공개 XML 피드에 대한 수집 경로를 구현했다.

## 공급원 선택과 변경 구조

| 자료 | 접근 방식 | 이번 결정 |
|---|---|---|
| [미 재무부 일별 액면수익률 곡선](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed) | `daily_treasury_yield_curve` 월별 공개 XML GET, 키 없음 | 10년물 `BC_10YEAR`를 `UST10Y_PAR` 후보로 원본 보관. `DGS10` 파일과 자동 혼합하지 않음 |
| [FRED API](https://fred.stlouisfed.org/docs/api/api_key.html) | 등록한 API 키 필요 | 현재 필수 경로로 채택하지 않음. 다른 지표·과거 빈티지 확인에 필요해지면 별도 발급 |
| [ETF 종가 후보](https://databento.com/docs/datasets/equs-summary) | 시장 데이터 공급자와 권리 범위 확인 필요 | TLT·SPY 가격의 과거 버전, 분배금·분할 처리, 내부 연구·외부 서비스/파생 지표 표시 권리를 확인한 뒤 채택 |

`TreasuryYieldCollector`는 월별 요청 URL을 고정하고 인증 헤더 없이 읽기 전용
GET을 실행한다. HTTP 응답을 다 받은 뒤 UTC 시각을 기록해 실제 XML 바이트를
Base64로 불변 보관하고 SHA-256과 원본 보관 식별자를 연결한다. XML 관측 **날짜**,
금리값, `captured_at`은 서로 다른 필드다. 날짜만 있는 원본에 존재하지 않는
발표 시각을 만들어 넣지 않으며, 빈 10년물은 0으로 채우지 않는다. 잘못된
월·중복 날짜·미래 날짜·HTML 응답·NaN은 거부한다. 모델 B 패널은 이번에
연결하지 않았다. 응답 수집 시각만으로 이전 날짜의 정확한 게시 시각을 알 수
없고, 과거 응답의 빈티지나 ETF 정답 자료도 없기 때문이다.

`make collect-treasury PYTHON=.venv/bin/python TREASURY_MONTH=202610`로 수집을
시작할 수 있다. 출력은 `archived_research_only`와 원본 해시·날짜 범위만
보고한다. `data/raw/`은 Git 추적에서 제외한다.

## 검증과 실제 도달 범위

`make test PYTHON=.venv/bin/python`에서 전체 **148개 시험이 통과**했다. 신규
통합 시험 3개는 요청에 인증 헤더가 없는지, 수신 직후의 UTC 시각과 XML 바이트
SHA-256이 불변 원본에 함께 남는지, 같은 시각·응답의 재실행이 중복 저장되지
않는지를 확인한다. 요청 월과 맞지 않는 날짜, 중복·미래 관측, HTML 및 NaN
응답은 실패시키는 시험도 통과했다. `make quality PYTHON=.venv/bin/python`의
Ruff는 위반 0건, Pyright는 오류 0건·경고 0건이었다.

`make collect-treasury PYTHON=.venv/bin/python TREASURY_MONTH=202610`의 실제 HTTP
시도는 `collection_failed`로 끝났다. 이 환경에서는 재무부 도메인 직접 DNS
접근이 실패하고, 프록시 경로의 SOCKS 추가 패키지도 없었다. 따라서 이번
수집·원본 보관 검증은 합성 XML과 `httpx.MockTransport`에서만 성립하며,
이 환경에서 실제 원격 응답을 받았다고 쓰지 않는다.

## 다음 수집 게이트

- [x] 금리 수집 코드는 키 없는 공식 원천과 고정된 월별 요청을 사용한다.
- [x] 실제 수신 직후 UTC 시각, 원본 XML, 해시를 불변 보관하는 코드를 만든다.
- [ ] 네트워크 가능한 환경에서 실제 응답의 필드·버전·수신 시각을 확인한다.
- [ ] ETF 가격 공급원의 실제 과거 수정 버전과 사용·표시 권리를 확인한다.
- [ ] 종목별 공통 날짜와 당시 사용 가능 시각을 검증한 뒤 비공개 A/B를 평가한다.

즉 **금리 수집을 시작하는 데 API 키가 선행 조건은 아니다.** SPY/TLT의
신뢰 가능한 예측 성능 평가에는 키 자체보다 시점별 가격·기업행동 자료와
그 권리·독립 시험 기간이 더 큰 선행 조건이다.

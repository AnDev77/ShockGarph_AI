# QQQ·SPY 위젯 기반 첫 화면 리뷰

2026-10-28. 사용자 결정에 따라 첫 배포의 가격 화면은 TradingView 무료 삽입 차트로 구성한다. 별도 공급원 계약 전까지 자체 가격 수치·과거 반응·예측 결과를 화면에 내보내지 않는다.

## 시작 기준과 변경량

기존 `apps/web`에는 README만 있었고 화면 코드가 없었다. 이번 변경은 정적 홈 `index.html`, 스타일 `market.css`, 종목 전환 `market.js`, 사용 방법 README의 화면 네 파일과 데이터 파이프라인 독서 가이드 및 이 리뷰다. QQQ와 SPY는 버튼으로 선택한다. 위젯은 각각 `NASDAQ:QQQ`, `AMEX:SPY` 식별자를 사용하고 가격 전달·렌더링은 공급자의 삽입 코드가 맡는다. 등록 가능한 종목은 두 코드로 고정해 임의 HTML이나 외부 링크가 입력으로 들어갈 수 없다.

## 외부 근거와 권리 경계

- [TradingView 위젯 소개](https://www.tradingview.com/widget/)는 기본 브랜드가 포함된 무료 웹 삽입을 제공한다. [새 Web Component 코드](https://www.tradingview.com/widget-docs/whats-new/)의 모듈 주소와 `symbol` 속성을 사용한다.
- 위젯은 [자체 서버에 접속해 데이터를 표시](https://www.tradingview.com/widget-docs/widget-formats/)한다. TradingView는 위젯 가격을 우리 계산에 넘기는 [시장 데이터 API를 제공하지 않는다](https://www.tradingview.com/widget/). 사용자 브라우저의 외부 접속·표시 지연·광고 및 브랜드 정책은 배포 전 실제 페이지에서 다시 확인한다.
- [Alpaca의 API 데이터 재배포 금지](https://alpaca.markets/support/redistribute-alpaca-api)에 따라 별도 비공개 연구 가격을 차트에 주입하거나 위젯에서 가격을 추출하지 않는다. 게시 권리가 확인된 별도 공급원 없이는 QQQ·SPY 과거 충격 수치를 서비스 API에 올리지 않는다.
- 공식 발표 링크는 [연준](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm), [BLS](https://www.bls.gov/schedule/news_release/current_year.asp), [BEA](https://www.bea.gov/news/schedule)의 일정 원문으로 향한다. 발표 예정·실제 발표·수집 시각을 연결한 자동 API는 아직 없다.

## 중간·완료 검증과 남은 조건

정적 HTML 파서로 QQQ·SPY 코드, 연준/BLS/BEA 세 공식 링크와 가짜 발표 날짜의 부재를 확인했다. Node 구문 검사와 DOM 대역 시험은 두 종목의 차트 속성·원문 링크·버튼 상태 전환을 확인했다. 로컬 wheel 빌드와 필수 소스 7개 내용 검사, Ruff·Pyright 오류·경고 0건, 전체 Python 시험 183개가 통과했다. 이 시험은 아직 브라우저의 외부 위젯 로드나 모바일 시각 배치를 확인하지 않는다.

중간 장애: Playwright 패키지는 있지만 브라우저 실행 파일이 없어 실제 화면 자동 시험을 시작하지 못했다. 임시 개발 서버도 이 실행 환경의 별도 프로세스에서 연결되지 않아 로컬 HTML 파일 파서로 범위를 줄였다. 외부 위젯 실제 로드, 브라우저 개인정보·쿠키 고지, 모바일 배치는 배포 전 별도 브라우저 통합 확인이 필요하다. 로그인·채팅·관심 목록과 과거 반응 화면은 이번 변경에 포함하지 않는다. 연구 성능과 공개 가격의 재배포 권한은 `HOLD`; 제품 수요도 방문자 행동 검증 전까지 `HOLD`다. 원격 PR 게이트 결과는 실행 후 PR에 기록한다.

## 객관적 검토

이 화면은 허가받은 공급자의 표시 경로와 공식 자료 탐색 입구를 빠르게 제공한다. 우리 계산 결과와 위젯의 가격이 같은 자료라고 주장하지 않으며 사건의 인과 효과도 보여주지 않는다. 제품의 차별성은 다음 발표를 잘 정리하고, 공개 허가가 확보된 후 같은 기준의 QQQ·SPY 과거 반응을 정확히 붙일 때 검증할 수 있다. 현재 구현만으로 금융 예측 서비스의 효용이나 10월 31일 운영 배포 준비를 판정할 수 없다.

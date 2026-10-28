# ShockGraph 데이터 파이프라인을 읽는 순서

현재 `main`과 초안 PR을 구분해 읽는다. 화면 위젯은 TradingView가 브라우저에 직접 제공하며, 아래 비공개 Alpaca 파이프라인의 가격을 소비하지 않는다. QQQ 선택 수집은 [초안 PR #12](https://github.com/AnDev77/ShockGarph_AI/pull/12)에 있고, `main`의 예약 수집은 TLT·SPY다. 관심 목록·사건 카드 API는 [초안 PR #11](https://github.com/AnDev77/ShockGarph_AI/pull/11)이며 공식 발표 자동 수집과 실제 운영 DB 연결은 별개다.

## 가격이 들어와 평가되기까지

1. **예약과 중복 방지:** `.github/workflows/private-forward-capture.yml`에서 시작한다. `scripts/check_capture_due.py`가 마지막 완료 거래일의 R2 기록 유무를 검사해 새 고유 날짜일 때만 수집한다. 예약 등록과 실행 성공, 새 날짜 보관은 각기 다른 판정이다.
2. **API 요청:** `scripts/collect_alpaca_prices.py`가 종목·기간을 받아 `apps/collector/shockgraph_collector/alpaca_bars.py`의 `AlpacaDailyCollector.collect()`를 호출한다. 두 조정 버전의 응답, 인증 처리, 페이지 반복과 값 검사가 여기 있다. 기본 종목은 TLT·SPY이고 PR #12의 QQQ는 명시적으로 선택할 때만 별도 실행한다.
3. **불변 원본과 거래일:** `packages/data_pipeline/shockgraph_data_pipeline/raw_store.py`가 수신 바이트·해시·시각을 보존한다. `daily_price_import.py`가 정규화·중복/누락/시각 검사를 하고, `market_calendar.py`가 예상 나스닥 거래일과 마감을 만든다. `trading_time.py`는 예측에 사용할 수 있는 시각의 경계를 다룬다.
4. **비공개 보관과 재검증:** `scripts/archive_forward_capture.py`가 검증한 원본과 manifest를 R2에 한 번만 쓰고 다시 읽어 해시를 확인한다. `scripts/audit_private_capture.py`는 마지막 index와 날짜별 목록을 독립 경로로 감사한다. 저장소 원본·가격·비밀값은 공개 로그와 PR에 넣지 않는다.
5. **위험 계산과 정답:** `packages/risk_engine/shockgraph_risk/forward_risk_capture.py`에서 사전 예측 기록을 만든다. `scripts/score_archived_forward.py`는 이후 가격 빈티지에서 정답 기간이 끝난 것만 골라 첫 유효 예측과 첫 성숙 정답본을 짝지어 비공개 점수를 기록한다. 합성 시험의 성공은 실제 미래 성능이 아니다.
6. **과거 탐색은 별도:** `scripts/analyze_alpaca_history.py`는 현재 수정 가격의 과거 이력을 재계산해 후보를 탐색한다. 이 수치를 독립적인 사전 성능으로 옮기지 않는다. 관련 회귀 시험은 `tests/integration/test_alpaca_bars.py`, `test_private_forward_archive.py`, `test_snapshot_holdout_cli.py`와 `tests/unit/test_daily_price_import.py`부터 보면 된다.

## 화면과 공식 사건 자료를 읽을 때

- `apps/web/index.html` → `market.js` → TradingView 위젯은 **표시 경로**다. 위젯 데이터가 Python 수집기나 자체 분석 모델로 들어오는 연결은 없다. 정적 화면은 공식 연준/BLS/BEA 일정의 원문 링크만 제공한다.
- 공식 발표의 원본 수집기는 아직 없으며, PR #11의 `apps/api/shockgraph_api/app.py`와 `watchlist.py`는 회원별 관심 목록·사건 카드의 **계약과 임시 구현**이다. 로그인 최종 소유자는 계획상 Java이며 실제 두 서버 연동은 미검증이다.
- 이후 공식 사건 입력을 붙일 때는 예정 시각, 실제 공개 시각, 수집 시각, 개정본을 분리하고 발표 전 예측에 미래 자료가 들어가지 않는지 검사해야 한다. 공개 QQQ·SPY 과거 반응 수치는 별도 표시 권한이 확보되기 전까지 화면에 없다.

처음에는 **워크플로 → 수집 CLI → collector → raw_store/import/calendar → archive/audit → forward score** 순서로 함수 호출을 따라가면 된다. 화면은 마지막에 별도로 보며, 비공개 분석과 위젯 표시를 하나의 가격 공급망으로 오해하지 않는 것이 핵심이다.

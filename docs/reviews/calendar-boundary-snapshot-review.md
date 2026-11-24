# 거래일 달력 종료 시 원본과 정답 보존

기준일: 2026-11-24 KST. 진행 기능은 Python PR #20의 사전 예측 수집 복구다. 별도 PR이나 선행 PR 위의 분기를 추가하지 않는다.

## 시작: 원격 상태와 작업 범위

| 저장소 | main | 열린 PR 생성 순서 | 기준·CI·충돌 상태 |
|---|---|---|---|
| ShockGarph_AI | 6288f6c | #19(11/17) → #20(11/18) | 모두 main 기준 초안, 병합 가능. #20의 기존 cfb6d78 CI 45124184839 성공. 이번 커밋의 CI는 별도 확인 |
| doChallenge | b962053 | #37(11/24 01:24 UTC) → #38(06:00 UTC) | 모두 main 기준, 병합 가능. #37 일반 PR, #38 초안. 최근 PR 품질 검사 성공. main 정확한 SHA의 check-runs는 비어 있어 main CI 통과로 대체하지 않음 |
| shockgraph-web | 38e38b0 | #13(11/17) | main 기준 초안. 해당 head의 과거 CI 성공, 현재 main과 충돌. 자동 병합 불가 |

각 저장소 AGENTS.md, 현재 제품 방향, Python/웹 일일 계획을 읽었다. Java 일일 계획은 웹 문서를 참조한다. Python 문서의 과거 RAG 소유 내용은 최신 사용자·Java·웹 결정과 맞지 않으며 이를 정리하는 #19가 열려 있다. Java가 공시 RAG와 사용자 API, Python이 가격·예측 연구, React가 화면을 담당한다. 이 작업은 Python만 변경한다. Java 작업 트리에 기존 미커밋 변경 3개가 있어 보존했고, 웹 작업 트리는 깨끗했다. Python은 기존 build/dist 산출물 외 추적 파일이 깨끗한 cfb6d78에서 시작했다.

### 예약과 실제 예측 구분

main의 예약은 여전히 뉴욕 07:10이다. [최근 예약 실행 45291837572](https://github.com/AnDev77/ShockGarph_AI/actions/runs/45291837572)은 11/23 23:47:38 UTC(11/24 08:47:38 KST)에 생성됐고 작업은 성공했다. 그러나 로그 상태는 snapshot_only_preopen_gate_failed이며 읽기 감사·재고 감사·기존 공식 채점 단계 성공과 새 예측 저장은 다르다. 이전 실행 44807951562와 비교해 고유 예측 시작 거래일은 늘지 않았다. 비공개 개수·가격·점수·객체 키는 전재하지 않는다. 예약 지연의 GitHub 내부 원인은 확인하지 못했다.

## 확인된 문제와 설계 선택

검증된 달력은 2026-12-31까지다. 12/02 다음에는 20거래일, 12/03 다음에는 19거래일만 남는다. 더 큰 문제는 마지막 날의 미래 날짜 요청이 2027-01-01부터 2026-12-31까지의 역전 범위가 되어 오류를 내는 것이다. 기존 archive_capture는 원본 쓰기 후 이 오류를 내므로 보관 index 작성과 이후 채점을 막을 수 있었다. 이는 합성 시험으로 재현한 잠재 장애이며 아직 발생한 운영 사고라고 쓰지 않는다.

2027 Nasdaq 달력을 공식 자료에서 확인하지 못해 검증 범위를 연장하지 않았다. 달력 부족을 이유로 가격 수집 전체를 중단하면 이미 기록된 예측의 실제 정답 가격까지 잃으므로, 원본 보관과 새 예측 생성의 허용 조건을 나눴다. 5일만 별도 예측을 만드는 계약 변경도 하지 않았다.

## 바뀐 구조와 직접 볼 코드

| 경로 | 변경·이유 |
|---|---|
| packages/data_pipeline/shockgraph_data_pipeline/market_calendar.py | 검증 범위 상수와 reviewed_future_sessions 추가. 마지막 날은 빈 미래 일정, 미검증 연도·휴장일 기준일은 오류로 구분 |
| packages/data_pipeline/shockgraph_data_pipeline/capture_window.py | 동일 범위 상수를 사용해 수집 날짜 검사 기준 통일 |
| packages/risk_engine/shockgraph_risk/forward_risk_capture.py | 미래 정답 일정 조회를 공통 함수로 전환. 예측 기간 부족 시 기존 거부 정책 유지 |
| scripts/archive_forward_capture.py | 쓰기와 읽기 감사에서 공통 미래 일정 사용. 달력이 끝나도 snapshot_only_reviewed_calendar_exhausted index를 남겨 원본을 읽고 채점 가능 |
| scripts/audit_capture_timing.py | 별도 연말 예외 분기 대신 같은 일정 조회 사용 |
| scripts/check_capture_due.py | forecast_calendar_ready, last_supported_forecast_origin, calendar_end 제공. 달력 부족만으로 원본 수집을 건너뛰지 않음 |
| .github/workflows/private-forward-capture.yml | 부족한 달력의 경고와 마지막 지원 기준일 표시. 비공개 가격/점수는 출력하지 않음. 기존 마지막 단계의 실제 예측 저장 필수 검사는 유지 |
| scripts/check_wheel_contents.py | 배포 wheel에 market_calendar.py가 포함되는지 추가 확인 |
| tests/integration/test_private_forward_archive.py | 실제 연말 합성 캡처·readback·재고·동일 입력 재실행·사전 안내·이전 예측의 정답 채점 검증 |
| tests/unit/test_daily_price_import.py | 20/19/0거래일 경계와 휴장일·주말·검증 범위 밖 거부 검증 |

실행 흐름: 사전 검사에서 달력 한계를 알림 → 가격 원본 보관 → 미래 20거래일 부족 시 예측 없는 index 기록 → 독립 readback → 기존 예측을 새 가격으로 채점 → 해당 거래일의 새 예측 필수 감사는 미충족으로 실패. 따라서 원본 보존 성공을 새 예측 성공으로 표시하지 않는다. 2027년 가격 수집을 허용한 것은 아니다.

## 중간: 재현·오류·수정

- 먼저 7개 통합 사례를 추가했고, 관련 기존 사례와 함께 실행해 5개 실패·3개 성공을 확인했다. 마지막 날의 역전 범위 오류 2건과 사전 검사 필드 누락 3건이었다.
- 공통 미래 일정 함수로 바꾼 뒤 기존 달력 부족 테스트의 monkeypatch 대상이 옛 함수라 1건 실패했다. 실제 사용 함수로 교체했고 부족 시 원본만 남기는 기존 검증 강도는 유지했다.
- Ruff에서 테스트 1줄이 길이 제한을 1자 초과했다. 중간 변수를 사용해 수정했다.
- 최초 기관 자료 URL은 404여서 문서의 실제 BlackRock 공식 URL로 다시 열었다. 접근 실패를 근거 확인 성공으로 쓰지 않는다.

## 완료: 검증표와 작업량

| 항목 | 결과·범위 |
|---|---|
| make quality PYTHON=.venv/bin/python | Ruff 위반 0, Pyright 오류·경고·정보 0 |
| make test PYTHON=.venv/bin/python | 269개 성공, 기존 Starlette 사용 중단 경고 1개. 직전 255개 대비 14개 추가 |
| python -m build --wheel | 성공. 서버 설치·EC2 배포 시험과는 다름 |
| scripts/check_wheel_contents.py | 필수 소스 14개 포함 확인 |
| git diff --check | 공백 오류 없음 |
| 원격 PR 게이트 | 새 커밋 게시 후 해당 SHA로 확인하여 PR 본문에 링크 기록 |
| R2/EC2 운영 변경 | 없음. 실제 계정 비밀값·가격을 가져와 새 실행하지 않음 |

새 통합 시험은 12/03·12/24·12/31 원본 전용 보관이 독립 읽기 감사까지 통과하고 예측 개수를 증가시키지 않는지 확인한다. 동일 입력·동일 receipt 재실행은 추가 객체를 만들지 않으며, receipt 시각이 다른 모든 재실행을 제거한다고 주장하지 않는다. 마지막 지원 기준일 12/02의 합성 예측은 12/31 합성 원본으로 TLT/SPY의 5·20일을 채점할 수 있었다. 사전 검사는 달력 부족을 알리면서 원본 수집 due를 유지하며, 잘못된 연도·휴장일은 미래 거래일로 만들어내지 않는다. 이 시험은 합성 저장소와 합성 가격을 사용하므로 실전 예측 정확도 또는 실제 R2 보존을 증명하지 않는다.

작업량은 실행/패키지/워크플로 8개 파일, 시험 2개 파일, 본 리뷰와 Review.md 총 12개 파일이다. 기능은 달력 끝에서의 원본·정답 보존 하나다. 기존 비공개 진행/장애/검증표 전체를 업로드하지 않고 본 리뷰의 시작·중간·완료 표로 안전한 기록을 남겼다.

## 공식 자료 대조와 연구 판단

- [Nasdaq 공식 달력](https://www.nasdaqtrader.com/Trader.aspx?id=Calendar), 확인 2026-11-24: 공개 표는 2026년이며 추수감사절·크리스마스 전 조기 종료를 확인했다. 이 페이지에서 2027년 표는 확인하지 못했다. [NYSE 공식 일정](https://www.nyse.com/markets/hours-calendars)은 2027년을 포함하지만 다른 거래소의 자료로 Nasdaq 검증 완료를 선언하지 않는다.
- [연준 FEDS 2025.061r1](https://www.federalreserve.gov/econres/feds/linear-and-nonlinear-econometric-models-against-machine-learning-models.htm), 2026-09-02 개정, 이번에 공식 초록 재확인: 예측 기간별 모형 순위가 달라지고 ML이 계량 모형 전반보다 일관되게 낫지는 않다. 따라서 5·20일 정의와 공통 평가 날짜를 보존하는 이번 수정이 필요하다. 현재 일봉 기반 변동성을 해당 실현 변동성 연구와 같은 입력으로 취급하지 않는다. 이번에는 논문 재현·모형 추가를 하지 않았다.
- [BlackRock 자본시장 가정](https://www.blackrock.com/institutions/en-global/institutional-insights/thought-leadership/capital-market-assumptions), 페이지 기준 2026년 11월, 자료 기준 9월 30일: 장기 자산배분의 시나리오와 불확실성을 다룬다. 이를 우리 5·20일 종목 예측 성과나 수요 증거로 사용하지 않는다.

객관적 평가: 연말 원본 보관 중단과 기존 예측의 정답 채점 차단을 재현·수정한 것은 유효한 소프트웨어 진전이다. 그러나 오늘 새 독립 예측 표본을 만들거나 성능을 향상한 것은 아니다. main의 늦은 예약 실행 문제는 #20 병합·실행 후 실제 신규 거래일 예측 readback으로 확인해야 한다. 달력 확장은 공식 Nasdaq 2027 일정과 예외 휴장 공지 확인 뒤 별도 검토가 필요하다. 예측 성능과 제품 수요는 HOLD다.

## 남은 외부 조건

- #20 병합 승인과 main 반영 후 실제 예약 시각·신규 예측 확인. 자동 병합하지 않는다.
- 2027년 거래소 공식 달력 검증. 현재 12/03부터 새 20일 예측은 계속 보류되며 이번 수정이 이 한계를 없애지는 않는다.
- EC2 권한·TLS·SMTP·승인 main의 CI·실회원/API/두 브라우저 채팅·Blue/Green 전환/되돌리기·공유 MySQL/Redis·스키마 공존·데이터 보존은 이 Python 시험에서 검증하지 않았다. 회원 배포 성공을 주장하지 않는다.

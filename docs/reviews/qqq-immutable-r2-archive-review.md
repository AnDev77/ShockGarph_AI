# QQQ 비공개 R2 원본 불변 보관 리뷰

2026-10-28. 초안 PR #12의 QQQ 실제 SIP 수집은 성공했으나 Actions 실행기 종료와 함께 원본이 사라졌다. 이번 변경은 **비공개 연구 원본의 지속 보관·재조회** 한 건을 추가한다. TLT·SPY 예약 수집과 5·20일 사전 위험 예측·공식 채점의 기존 R2 경로는 변경하지 않는다.

## 시작·중간·완료 근거와 작업량

| 단계 | 근거 | 판정 |
| --- | --- | --- |
| 시작 | [QQQ 실수집 실행](https://github.com/AnDev77/ShockGarph_AI/actions/runs/40640556894)의 수집·구조 검사는 성공. 기존 리뷰는 임시 디스크만 보관한다고 명시 | QQQ 원본 빈티지 재검증은 불가능 |
| 시험 먼저 | `scripts.archive_private_research_capture`가 없어서 통합 시험 수집 실패 | 새 보관 경로가 필요한 실패 시험 확보 |
| 구현 중간 | QQQ manifest의 단일 종목·비공개 권한·정규화 CSV·원본 응답·거래일을 먼저 검사한 뒤 전용 `qqq-captures/` 경로에 저장. R2에서 index와 각 원본을 다시 읽어 SHA-256과 쓰기 시각을 감사 | 기존 TLT·SPY `captures/`와 예측을 섞지 않음 |
| 완료 검증 | 로컬 대상 통합 시험 3개, 전체 188개 통과. wheel 빌드와 필수 소스 7개 검사, Ruff·Pyright 오류·경고 0건. 재실행 무중복, 원본 변조 거부, 비QQQ 자료·예산 초과 시 쓰기 전 실패, CLI의 키·가격 비노출 확인 | 실제 원격 R2 실행은 신규 Actions 결과를 별도 확인 |

변경 경로는 연구용 R2 보관 스크립트, QQQ CSV 읽기 허용(기존 TLT·SPY 분석 진입점은 여전히 두 종목 고정), 비공개 Actions 작업, 통합 시험, 이 기능 리뷰와 기존 QQQ 리뷰다. 비밀값·원본 가격·객체 key·오차 수치는 출력하거나 공개 파일로 올리지 않는다. 워크플로의 QQQ 작업은 기능 브랜치 푸시에서만 실행되며 `main`의 공식 TLT·SPY 예약 수집·점수와 독립이다. 해당 브랜치를 main에 병합해도 QQQ 자동 **매일** 보관은 시작되지 않는다.

## 운영 장애와 검증 경계

R2 설정 누락은 비밀값 자체 대신 설정 부족 상태만 출력한다. 버킷 저장량 검사가 실패하면 업로드 전 중단한다. 원본 일부 저장 뒤 네트워크가 끊기면 같은 바이트의 재시도를 허용하고, 다른 바이트가 같은 키에 있으면 충돌로 거부한다. 원본·index 해시 또는 R2 UTC 기록 시각이 맞지 않으면 읽기 감사가 실패한다. 실제 R2 보관이 성공했는지는 Actions의 보관·독립 재조회 단계 성공으로만 판단한다.

## 연구와 제품의 독립 판정

[연준 FEDS 2025-061의 2026년 9월 개정본](https://www.federalreserve.gov/econres/feds/2025.htm)은 S&P 500과 개별 주식 40개의 **고빈도 실현 변동성**을 1·5·월간 기간에 여러 계량 모델과 ML로 비교한다. 현재 프로젝트의 일봉 기반 TLT 5·20일 정답이나 QQQ 원본 저장은 같은 목표·빈도가 아니다. 공통 예측 시작일, 당시 이용 가능한 버전, 이후 성숙한 독립 정답과 기준선이 확보되기 전에는 모델 우위를 주장하지 않는다.

[BlackRock의 2026년 자본시장 가정](https://www.blackrock.com/institutions/en-global/institutional-insights/thought-leadership/capital-market-assumptions)은 여러 거시 시나리오와 장기 자산 수익·불확실성을 다룬다. [위험 시나리오 대시보드](https://www.blackrock.com/corporate/insights/blackrock-investment-institute/interactive-charts/geopolitical-risk-dashboard)의 역사적 유사 사건·자산 반응은 연구 질문을 잡는 참고 자료다. QQQ·SPY의 당일 거시 발표 효과나 이 프로젝트의 예측 성능을 입증하는 근거가 아니다. 소프트웨어 품질 통과, 실제 예측 성능, 제품 수요는 각각 별도 판정하고 후자 둘은 `HOLD`한다. TradingView 위젯은 공개 화면의 별도 제공 경로이며 비공개 Alpaca 수치를 화면에 재배포하지 않는다.

## 신규 사전 기록의 운영 확인

[main의 10월 27일 예약 실행](https://github.com/AnDev77/ShockGarph_AI/actions/runs/40541934996)은 가격 보관과 원격 재조회가 성공했지만 해당 index의 예측 건수는 0이었다. 고유 사전 예측 거래일 수는 늘지 않았다. 실행이 개장 전 기록 문턱을 놓친 결과로 보이며, 예약 시각 변경은 별도 [초안 PR #10](https://github.com/AnDev77/ShockGarph_AI/pull/10)에 있으므로 여기서 중복 수정하지 않는다. 이 QQQ 보관 성공 여부와 TLT·SPY의 미래 정답 성숙을 혼동하지 않는다.

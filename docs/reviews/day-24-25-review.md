# 24~25일차 GitHub Actions 실데이터 검증 리뷰

## 작업 목표

개인 PC에만 존재하던 Alpaca 인증정보를 GitHub Actions Secret으로 관리하고, 공개 저장소에
키·원시 가격·사건별 수익률을 올리지 않으면서 CPI·ETF 검증을 반복 실행할 수 있게 한다.

## 변경 구조

- `.github/workflows/alpaca-cpi-validation.yml`: Kalshi·BLS 재수집, Alpaca 분봉 수집,
  사건 패널 생성, 가격 기준선 평가, 안전한 결과 보관
- `scripts/run_cpi_asset_pipeline.py`: `iex`와 `sip` 피드 선택 지원
- `scripts/export_alpaca_validation_summary.py`: 원시 가격과 사건별 예측을 제거하고 집계 결과만 출력
- `tests/unit/test_alpaca_validation_summary.py`: 비밀값·개별 수익률 제외와 입력 해시 연결 검증

## 보안·데이터 공개 경계

워크플로는 `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`를 GitHub Actions Secret에서만 읽는다.
값 자체를 출력하지 않고 존재 여부만 검사한다. 원시 API 응답, 분봉 CSV, 사건별 수익률 패널은
러너 종료와 함께 폐기한다. Artifact에는 표본 수, 결측 상태 집계, 해시, 기준선 집계 지표만 남긴다.

## 실행 방법

`feat/analytics`에 관련 코드가 푸시되면 IEX 피드로 자동 실행된다. GitHub의 `Actions`에서
`Alpaca CPI 자산 검증`을 선택해 수동 실행할 때는 `iex` 또는 `sip`를 고를 수 있다.

## 검증 결과

- 로컬 `make quality`: Ruff 통과, Pyright 오류·경고 0개
- 로컬 `make test`: 113개 통과, Starlette TestClient 사용 중단 예정 경고 1개
- `git diff --check`: 통과
- GitHub Actions 실제 Alpaca 호출: 워크플로 푸시 후 확인 예정

## 사용자 점검표

- [ ] Actions Secret 두 이름이 코드와 정확히 일치하는가
- [ ] 워크플로 로그에 키나 인증 헤더가 출력되지 않는가
- [ ] `bar_rows`와 `common_events`가 0보다 큰가
- [ ] `coverage_status_counts`에서 주요 결측 원인을 확인했는가
- [ ] `test_events`가 10개 미만이면 성능을 주장하지 않는가
- [ ] SIP 실행이 거절되면 IEX 결과와 구독 제한을 구분했는가

# 24~25일차 GitHub Actions 실데이터 검증 리뷰

## 작업 목표

개인 PC에만 존재하던 Alpaca 인증정보를 GitHub Actions Secret으로 관리하고, 공개 저장소에
키·원시 가격·사건별 수익률을 올리지 않으면서 CPI·ETF 검증을 반복 실행할 수 있게 한다.

## 변경 구조

- `.github/workflows/alpaca-cpi-validation.yml`: Kalshi·BLS 재수집, Alpaca 분봉 수집,
  사건 패널 생성, 가격 기준선 평가, 안전한 결과 보관
- `scripts/run_cpi_asset_pipeline.py`: `iex`와 `sip` 피드 선택 지원
- `scripts/export_alpaca_validation_summary.py`: 원시 가격과 사건별 예측을 제거하고 집계 결과만 출력
- `scripts/analyze_event_coverage_losses.py`: 사건별 확률·가격 교집합 손실과 제외 사유 진단
- `tests/unit/test_alpaca_validation_summary.py`: 비밀값·개별 수익률 제외와 입력 해시 연결 검증

## 보안·데이터 공개 경계

워크플로는 `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`를 GitHub Actions Secret에서만 읽는다.
값 자체를 출력하지 않고 존재 여부만 검사한다. 원시 API 응답, 분봉 CSV, 사건별 수익률 패널은
러너 종료와 함께 폐기한다. Artifact에는 표본 수, 결측 상태 집계, 해시, 기준선 집계 지표만 남긴다.

## 실행 방법

`feat/analytics`에 관련 코드가 푸시되면 SIP 피드로 자동 실행된다. GitHub의 `Actions`에서
`Alpaca CPI 자산 검증`을 선택해 수동 실행할 때는 `iex` 또는 `sip`를 고를 수 있다.

## 검증 결과

- 로컬 `make quality`: Ruff 통과, Pyright 오류·경고 0개
- 로컬 `make test`: 113개 통과, Starlette TestClient 사용 중단 예정 경고 1개
- `git diff --check`: 통과
- GitHub Actions 실제 Alpaca IEX 호출: 성공

## 최초 실데이터 실행 결과

2026-09-30 실행한 [GitHub Actions 실행 1번](https://github.com/AnDev77/ShockGarph_AI/actions/runs/36651767076)은
Secret 확인, 품질 검사, 113개 테스트, 공개 입력 재수집, Alpaca 호출, 결과 보관까지 모두 성공했다.

| 항목 | 결과 |
|---|---:|
| 피드 | `iex` |
| CPI 발표 사건 | 53 |
| 실제 ETF 분봉 | 539 |
| 커버리지 판정 행 | 308 |
| 시작 봉 결측 | 298 |
| 종료 봉 결측 | 10 |
| SPY·TLT·GLD 공통 완전 사건 | 0 |
| 기준선 평가 | `insufficient_test_events` |

인증과 Alpaca API 접근은 정상이다. 현재 병목은 IEX 피드에서 과거 CPI 발표시각의 장전 거래가
희소해 정확한 시작 봉을 확보하지 못한다는 점이다. 분봉을 임의 보간하지 않았으므로 모델 평가는
실행하지 않았고 성능 지표도 비워 두었다. 다음 판단은 SIP 수동 실행의 구독 가능 여부와 커버리지다.

## SIP 실데이터 실행 결과

2026-09-30 실행한 [GitHub Actions 실행 2번](https://github.com/AnDev77/ShockGarph_AI/actions/runs/36652730956)은
SIP 인증과 전체 파이프라인을 성공적으로 완료했다.

| 항목 | 결과 |
|---|---:|
| 피드 | `sip` |
| CPI 발표 사건 | 53 |
| 실제 ETF 분봉 | 5,051 |
| 가격창 완전 사건 | 26 |
| Kalshi 확률까지 결합된 모델 공통 사건 | 11 |
| 초기 학습 사건 | 5 |
| 표본 외 시험 사건 | 6 |
| 최소 시험 사건 | 10 |
| 기준선 평가 | `insufficient_test_events` |

SIP 권한과 과거 장전 분봉 접근은 정상이며 IEX보다 가격 커버리지가 크게 개선됐다. 그러나
품질을 통과한 Kalshi 확률과 가격창의 교집합은 11건이므로, 초기 5건 학습 후 시험 사건은 6건뿐이다.
현재 수치로 성능 우위를 주장하지 않고 표본 확대 또는 희소표본용 평가 설계를 다음 단계로 검토한다.

## 사용자 점검표

- [ ] Actions Secret 두 이름이 코드와 정확히 일치하는가
- [ ] 워크플로 로그에 키나 인증 헤더가 출력되지 않는가
- [ ] `bar_rows`와 `common_events`가 0보다 큰가
- [ ] `coverage_status_counts`에서 주요 결측 원인을 확인했는가
- [ ] `test_events`가 10개 미만이면 성능을 주장하지 않는가
- [ ] SIP 실행이 거절되면 IEX 결과와 구독 제한을 구분했는가

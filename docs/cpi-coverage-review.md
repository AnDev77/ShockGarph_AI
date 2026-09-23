# CPI·미국 ETF 데이터 커버리지 점검

점검일: 2026-09-22

2026-09-23에 기본 도메인 연결과 특정 CPI 이벤트의 발표 직전 분봉을 추가 점검했다.
이번 환경의 접근 결과와 각 자료 수준에 맞는 분석 방법은
[Kalshi CPI 접근·방법론 검토](kalshi-cpi-access-methods.md)를 따른다.

## 이번 실행 결과

`scripts/probe_cpi_coverage.py --max-pages 10`으로 공개 GET 접근을 점검했다.
이 실행은 원본 응답이나 시장 확률·가격을 저장하지 않는다.

| 항목 | 이번 환경의 결과 | 판단 |
|---|---|---|
| Kalshi `/historical/cutoff` | HTTP 403 | 현재·과거 분할 경계 조회 실패 |
| Kalshi `/markets`, 시리즈 KXCPI | HTTP 403 | 현재 CPI 계약 목록 확인 실패 |
| Kalshi `/historical/markets`, 시리즈 KXCPI | HTTP 403 | 과거 CPI 계약 목록 확인 실패 |
| 발표 전 확률 캔들 | 목록 확인 실패로 진행하지 않음 | 확보 건수 미확인 |
| FRED 환경변수 | `FRED_API_KEY` 미설정 | 거시 기대·빈티지 자료 수집 미실행 |
| 미국 ETF 공급원 환경변수 | `ALPHA_VANTAGE_API_KEY` 미설정 | SPY·TLT·GLD 가격 수집 미실행 |
| CPI·가격·기대 자료의 공통 기간 | 확인 불가 | 실데이터 학습 준비 미완료 |

403이 공급자 응답인지 실행환경 네트워크 경계에서 발생한 응답인지는 이번 점검에서
확정하지 않았다. 이를 Kalshi 서비스 전체 장애나 데이터 부재로 해석하지 않는다.
이전 문서의 과거 표본 수는 당시 점검 기록이며 이번 실행에서 재확인한 수치가 아니다.

## 재현과 해석

```bash
python scripts/probe_cpi_coverage.py --max-pages 10
```

스크립트는 페이지 상한에 도달하면 `partial`을 반환한다. 이때 건수는 관측한 범위뿐이며
전체 역사 자료 수가 아니다. 반복 커서는 오류로 처리한다. 현재·과거 각 결과의 이벤트 수는
중복될 수 있으므로 단순히 더하지 않는다. 스크립트는 두 계층의 완전한 결합 건수를 주장하지 않는다.
또한 API 키가 설정됐다는 사실만으로 권한·요금제·이용조건이 확인되지는 않는다.

이 환경에서는 SOCKS 프록시 지원 모듈이 없어 첫 연결 생성이 실패했다.
검증 환경에만 `socksio`를 설치한 뒤 위 점검을 실행했다. 프로젝트의 운영 의존성은 추가하지 않았다.
같은 오류가 나타나는 환경에서는 `python -m pip install 'httpx[socks]'`를 사용할 수 있다.

## 다음 데이터 연결 순서

1. 접근 가능한 승인 환경에서 목록 커버리지를 다시 점검한다.
2. 필요한 CPI 정의·임계값·발표시각을 확정하고 발표 전 확률 관측을 확인한다.
3. 허용된 ETF 가격·최초 발표치·당시 기대값을 동일 기간으로 확보한다.
4. `ResearchDataset` 계약에 맞춰 정규화하고 발표·원본 해시·기업행동 처리 근거를 보존한다.
5. 공통 기간, 발표 수, 결측·제외 비율, 신선도·호가 품질을 보고한 뒤 연구 파이프라인을 실행한다.

관련 기존 판단: [초기 데이터 가용성](data-feasibility.md),
[자산 공급원 검토](data-source-gate-b.md).

공식 문서 확인: Kalshi는 현재·과거 계층과 데이터별 cutoff, 역사 시장 목록·캔들 경로를 제공한다.
이 사실은 특정 계정·환경의 접근 성공이나 공통 학습 자료 확보를 보장하지 않는다.

- [Kalshi 역사 데이터](https://docs.kalshi.com/getting_started/historical_data)
- [Kalshi 역사 시장 목록](https://docs.kalshi.com/api-reference/historical/get-historical-markets)
- [Alpha Vantage 데이터 문서](https://www.alphavantage.co/documentation/)

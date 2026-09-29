# 22~23일차 분석 화면 구현 리뷰

## 작업 목표

검증된 CPI 예측시장 연구 결과와 ETF 분석 준비 상태를 사용자가 직접 구분해 확인할 수 있는
모바일 우선 분석 화면을 구현했다. 화면은 FastAPI 응답만 사용하며, 가격 데이터가 없는 경우
수익률이나 상승확률을 임의로 채우지 않는다.

## 변경된 구조

- `apps/web/app`: Next.js App Router의 레이아웃, 페이지, 전역 스타일
- `apps/web/components/dashboard.tsx`: CPI 연구 결과, 자산·기간 선택, 로딩·오류·표본 부족 상태
- `apps/web/components/provider.tsx`: Chakra UI v3 공급자
- `apps/api/shockgraph_api/app.py`: 로컬 웹 출처 CORS와 연구 결론 식별자
- `tests/integration/test_analysis_api.py`: 연구 결론과 CORS 회귀 테스트
- `Makefile`: `web-dev`, `web-build` 실행 명령

## 화면 해석 기준

왼쪽 카드는 Kalshi CPI 계약 확률의 예측 정확도 연구를 보여준다. Brier 점수는 낮을수록 좋으며,
현재 검증 자료에서는 원시 시장확률이 누적 과거비율보다 낮은 오차를 보였다. 이 결과는 ETF의
상승확률이나 기대수익률을 의미하지 않는다.

오른쪽 패널은 사용자가 SPY·TLT·GLD와 발표 후 5분·30분 구간을 선택하는 영역이다. 실제 Alpaca
분봉 패널이 아직 생성되지 않았으므로 API의 `insufficient_data`를 그대로 보여준다. 대시(—)는 0이
아니라 미산출 상태다.

## 검증 결과

- `npm --prefix apps/web run typecheck`: 통과
- `npm --prefix apps/web run build`: 통과
- `make quality`: 통과
- `make test`: 111개 테스트 통과
- API CORS: `http://localhost:3000`과 `http://127.0.0.1:3000` 허용
- 비밀정보: `.env`와 API 키를 커밋하지 않음

## 사용자가 확인할 사항

- [ ] `SHOCKGRAPH_RESEARCH_METADATA`에 실제 `metadata.json` 경로를 지정했는가
- [ ] API의 `/health/ready`가 `ready`를 반환하는가
- [ ] CPI 카드의 사건 수와 Brier 점수가 연구 산출물과 일치하는가
- [ ] SPY·TLT·GLD 선택 시 요청 종목이 바뀌는가
- [ ] 5분·30분 선택 시 요청 구간이 바뀌는가
- [ ] 가격 패널 생성 전에는 숫자 대신 `가격 자료 검증 대기 중`이 표시되는가
- [ ] 360px 너비에서 가로 스크롤 없이 모든 선택 버튼을 사용할 수 있는가

## 다음 작업

발급받은 Alpaca Market Data 키를 로컬 환경변수로만 주입한 뒤 ETF 분봉 수집과 사건 패널 생성을
실행한다. 품질 게이트를 통과한 실제 패널이 만들어지면 `/v1/analysis`가 표본 수, 불확실성,
수익률 분포를 반환하도록 확장하고 같은 화면에 검증된 값만 표시한다.

# 판단 기록 경쟁성 재평가와 사건 분석 리포트 가치 리뷰

검토일: 2026-10-20

## 사용자 지적과 변경 이유

이전 [제품 선택 문서](../product-goal-and-fallback.md)는 예측 성능이 나쁘면
발표 전 판단을 기록·복기하는 페이지와 비동기 커뮤니티를 사용자 가치 후보로
두었다. 그러나 [Notion의 트레이딩 저널 템플릿](https://www.notion.com/templates/category/trading-journal)
만으로도 기록장 기능은 구현할 수 있다. 발표 일정은
[FRED](https://fred.stlouisfed.org/releases/calendar), 금리 결정 확률과
이력은 [CME FedWatch](https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html),
경제 일정·컨센서스는 [Koyfin](https://www.koyfin.com/data-coverage/global-economics/)의
제공 범위와도 비교해야 한다. 이 자료를 한 화면에 놓는 것만으로 차별성을
확정하지 않는다.

따라서 모델의 추가 예측력이 없더라도 무조건 커뮤니티를 출시한다는 경로를
제거했다. 별도 실험 가설은 **발표 전 이용 가능했던 기대·확률, 최초 발표값,
관측 구간을 명시한 TLT/금리 반응, 과거 유사 사건**을 자동으로 결합하는
재현 가능한 분석 리포트가 기존 도구를 오가는 수동 조사보다 실제로 유용한가다.
한 사건의 관련 시계열 움직임을 CPI만의 인과효과라고 설명하지 않는다.

작은 시범 리포트에서 동일 조사 과제의 완료 시간, 발표 시각·가격 구간·
출처 오류, 반복 사용 의사를 비교한다. 실제 우위가 없거나 라이선스·시점
자료를 확보하지 못하면 대안 제품과 일반 커뮤니티를 진행하지 않는다.
노트를 원하는 사용자에게는 필요할 때 Notion/Markdown 내보내기를 고려하며
별도 판단 기록장을 만들지 않는다. 토론은 검증된 리포트의 자료·해석을
논의하겠다는 반복 수요가 있을 때에만 보조 기능으로 검토한다.

## 문서·구현 경계

- [제품 명세](../../shockgraph-ai-project-spec.md), [제품 선택 기준](../product-goal-and-fallback.md),
  [화면](../product-ui-direction.md), [흐름](../project-flow.md),
  [아키텍처](../architecture.md), [주주 인증 후속](../shareholder-community-roadmap.md),
  [위험 방법론](../daily-risk-methodology.md), README·AGENTS를 같은 판단에 맞췄다.
- 데이터 수집·모델·API·웹의 실행 코드는 바꾸지 않았다. 자동 사건 리포트,
  수동 조사 비교, 로그인·커뮤니티는 아직 구현·실증되지 않았다.

## 검증과 사용자 점검

`make quality PYTHON=.venv/bin/python`의 Ruff 규칙 검사는 통과했고 Pyright는
오류 0개와 경고 0개를 보고했다. `make test PYTHON=.venv/bin/python`은
기존 가격 시점 선택·위험 계산·CPI 연구 경로를 포함한 계약·단위·통합 테스트
113개를 통과했다. 변경 대상 Markdown 8개에서 확인한 상대 링크 64개에는
누락 파일이 없었다. `git diff --check`는 변경된 문서의 공백 오류를 보고하지
않았다. 이 결과는 기존 코드의 회귀 점검이며 자동 리포트의 사용자 가치나
모델의 예측 성능을 입증하지 않는다.

- [ ] 판단 기록 자체를 차별점이라고 표현하지 않는가?
- [ ] 자료의 실제 공개 시점·최초 발표치·관측 구간이 한 리포트에 맞게 결합되는가?
- [ ] 자동 리포트가 수동 조사보다 시간·오류를 개선한다는 사용자 시험이 있는가?
- [ ] 개선 증거가 없을 때 종목방을 자동 출시하지 않는가?

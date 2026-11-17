# 브랜치 정리와 현재 작업 기준

기준일: 2026-11-17 KST. 사용자 요청에 따라 최신 관심 종목 RAG 브리핑 계획에 맞춰 원격 브랜치와 열린 PR을 정리했다.

## 결정과 이유

- 현재 작업은 #18 `feat/camt-filing-briefing` 하나다. Python은 공시 수집·검색·요약·검증·내부 조회와 Kafka 초안 작업 전달을 담당한다.
- 회원·관심 목록·외부 API는 Java doChallenge, 화면·차트는 shockgraph-web이 소유한다. Java main에 WatchlistController/Service/Repository와 V2 마이그레이션이 있음을 확인했다. Python 관심 목록 #11과 정적 홈 #13을 통째로 병합하지 않는다.
- 예측 워커·가격 수집·공식 점수·포트폴리오 리밸런싱은 별도 연구로 보관한다. 유효하지 않은 코드라는 뜻이 아니라 이번 출시 순서에서 제외한다는 뜻이다.
- #8~#17은 각 PR 본문에 이유·보관 경로·원래 head를 남기고 닫았다. #14→#15→#16→#17과 analytics→portfolio-risk→data-serving은 마지막 분기에 모든 선행 커밋이 포함됨을 확인해 묶었다.
- 원격 브랜치는 23개에서 10개로 줄었다: main 1개, 현재 기능 1개, archive/2026-11-17 아래 보관 8개. 병합 완료 8개와 보관으로 대체한 기존 13개 분기 이름을 삭제했다. 삭제한 커밋 이력은 모두 main 또는 보관 분기에서 도달 가능하다.

## 원래 이름과 복원 기준

| 원래 브랜치 | 정리 전 head SHA | 이력을 보존한 분기 | 처리 |
|---|---|---|---|
| `docs/managed-containers-serving-strategy` | `99ddf4af8aa50b9a79d20fa9f36f4defab14d805` | `main` | main 포함 확인 후 분기 삭제 |
| `feat/alpaca-price-snapshots` | `20091fce64f283877c960a6ef1623f5cda1b0c4d` | `main` | main 포함 확인 후 분기 삭제 |
| `feat/analytics` | `2ebfd0e67a0dd2fc5eadb70fb77c0c775fcf5e38` | `archive/2026-11-17/data-serving` | 보관 후 기존 분기 삭제 |
| `feat/camt-filing-briefing` | `dc6fe58b7053111a29a5176d681f4bfa87aff000` | `feat/camt-filing-briefing` | 현재 작업 유지 |
| `feat/daily-risk-baseline` | `a09245ff7e54f82c045370ce8aa28350d40960ac` | `main` | main 포함 확인 후 분기 삭제 |
| `feat/daily-risk-pivot` | `bfecffb621d71436f5e24712a911911ebc099c20` | `main` | main 포함 확인 후 분기 삭제 |
| `feat/data-serving` | `59ea3bc4c4e0ce68d91388a86b6b2fd7eaf8fe75` | `archive/2026-11-17/data-serving` | 보관 후 기존 분기 삭제 |
| `feat/five-day-finance-community-mvp` | `d3d8bbfdf62ac1642734be87aff5c50983f629ca` | `archive/2026-11-17/five-day-finance-community-mvp` | 보관 후 기존 분기 삭제 |
| `feat/indicator-capture-provenance` | `f6e35087e9474abc439470a3fec72bb2c2b7c6f8` | `main` | main 포함 확인 후 분기 삭제 |
| `feat/indicator-freshness-gate` | `149f5dd4ab8f9613c69ca5744087b536e70ea766` | `main` | main 포함 확인 후 분기 삭제 |
| `feat/market-widget-home` | `e0d3ec9e825eea0521216e5a2635b7b70c772be6` | `archive/2026-11-17/market-widget-home` | 보관 후 기존 분기 삭제 |
| `feat/official-evaluation-coverage` | `e58d609b8156338c334652c60153be2b45febed3` | `archive/2026-11-17/official-evaluation-coverage` | 보관 후 기존 분기 삭제 |
| `feat/official-score-metadata` | `a1dfb2f1a4d2256fab4107ba9ccea4048d877cf5` | `archive/2026-11-17/official-score-metadata` | 보관 후 기존 분기 삭제 |
| `feat/portfolio-point-in-time-panel` | `eb554811b096005658c078dc5a7294ca41037301` | `archive/2026-11-17/portfolio-withdrawal-cash-first` | 보관 후 기존 분기 삭제 |
| `feat/portfolio-rebalance-baselines` | `67bffbbdcdc6514a55bf4211850db9fe8549ffd8` | `archive/2026-11-17/portfolio-withdrawal-cash-first` | 보관 후 기존 분기 삭제 |
| `feat/portfolio-rebalance-direction` | `4ddad2a3bb8b1a72a5f041049fd8d03675932202` | `archive/2026-11-17/portfolio-withdrawal-cash-first` | 보관 후 기존 분기 삭제 |
| `feat/portfolio-risk` | `b667ef4ffbdfd502612bf31c4530514c957d1192` | `archive/2026-11-17/data-serving` | 보관 후 기존 분기 삭제 |
| `feat/portfolio-withdrawal-cash-first` | `1c9bf5152957f715a5806da581cee2aa00b53a36` | `archive/2026-11-17/portfolio-withdrawal-cash-first` | 보관 후 기존 분기 삭제 |
| `feat/preopen-capture-window` | `c32af56cef8b5d9cdfa9de922ef6821ed738183a` | `archive/2026-11-17/preopen-capture-window` | 보관 후 기존 분기 삭제 |
| `feat/qqq-private-intake` | `751eb8d455b6a92d138a1a9c1bb53362b1c201a8` | `archive/2026-11-17/qqq-private-intake` | 보관 후 기존 분기 삭제 |
| `feat/treasury-rate-collection` | `bc1627e1baa417a136b253f968be7d8f366fa086` | `main` | main 포함 확인 후 분기 삭제 |
| `feature/day-03-04-foundation` | `b5f84856f2d73e5e877493322a297cb89d98ee33` | `main` | main 포함 확인 후 분기 삭제 |
| `main` | `a993373ea694427933227f3efbf91db80ce7fe4b` | `main` | 기준 유지 |

원래 분기를 복원해야 한다면 해당 행의 SHA로 새 분기를 만든다. 보관 분기에서는 후속 개발하지 않는다. 필요한 기능은 최신 main에서 새 범위를 정하고 가져오며, 과거 AGENTS.md·제품 방향·일정 전체를 다시 병합하지 않는다. PR #14~#17을 원래 순서대로 다시 열 경우 각 원래 head와 base 분기를 먼저 복원해야 한다.

## PR별 분류

| PR | 판정 근거 |
|---|---|
| [#8](https://github.com/AnDev77/ShockGarph_AI/pull/8) | 공식 위험 점수 PostgreSQL 저장은 예측 연구 후속이며 현재 공시 RAG 출시의 선행 조건이 아니다. |
| [#9](https://github.com/AnDev77/ShockGarph_AI/pull/9) | 독립 예측 표본·정답 성숙 감사는 유효한 연구 기능이지만 이번 브리핑 출시 범위 밖이다. |
| [#10](https://github.com/AnDev77/ShockGarph_AI/pull/10) | 예측 수집 예약 시간 변경은 연구 운영 작업이며 RAG·LLM Kafka 작업 전달과 무관하다. |
| [#11](https://github.com/AnDev77/ShockGarph_AI/pull/11) | 회원·관심 목록은 Java doChallenge가 소유하고 현재 main에도 구현돼 있다. 이 초안의 Python JWT·PostgreSQL 관심 목록을 통째로 병합하면 소유권이 중복되고 과거 사건 중심 계획이 복원된다. 사건 조회·장애 설계는 향후 필요한 부분만 재검토한다. |
| [#12](https://github.com/AnDev77/ShockGarph_AI/pull/12) | QQQ 비공개 가격 수집·보관은 별도 연구 트랙이다. CAMT 우선 공식 공시 브리핑과는 독립이며 현재 공개 QQQ/SPY 차트의 필수 입력이 아니다. |
| [#13](https://github.com/AnDev77/ShockGarph_AI/pull/13) | 제품 화면은 shockgraph-web의 React 앱에서 관리한다. Python 저장소의 별도 정적 홈 화면은 중복이므로 통합하지 않는다. 파이프라인 안내는 이력으로 보존한다. |
| [#14](https://github.com/AnDev77/ShockGarph_AI/pull/14) | 현재 방향은 포트폴리오 위험·리밸런싱에서 관심 종목 RAG 브리핑으로 바뀌었다. 이 문서를 병합해 최신 방향을 덮어쓰지 않는다. |
| [#15](https://github.com/AnDev77/ShockGarph_AI/pull/15) | 리밸런싱 정책 기준선은 별도 연구로 보존하며 이번 주 브리핑 출시에는 포함하지 않는다. |
| [#16](https://github.com/AnDev77/ShockGarph_AI/pull/16) | 시점별 가격본 선택은 재활용 가능한 연구 기반이지만 브리핑 출시와 독립이다. |
| [#17](https://github.com/AnDev77/ShockGarph_AI/pull/17) | 현금 인출·비용 회계는 리밸런싱 연구 범위다. 이번 브리핑 출시에서 제외하고 #14~#17 전체 이력을 마지막 브랜치에 함께 보존한다. |
| [#18](https://github.com/AnDev77/ShockGarph_AI/pull/18) | 현재 RAG·Kafka 작업으로 유지. 실제 브로커·LLM·Java 연결은 별도 인수 조건. |

## 바뀐 파일과 추가 기능

실행 코드는 바꾸지 않았다. AGENTS.md에 진행 중 기능 하나와 보관 분기 재개 기준을 반영하고, 현재 제품 방향과 일일 계획을 최신 웹 계획 및 11/17 Kafka 결정에 맞췄다. Review.md는 이 기록으로 연결한다. 신규 런타임 기능은 없으며 작업 대기열·복원 기록·후속 우선순위를 정리했다.

## 시작·중간·완료 검증

- 시작: 원격 브랜치 23개, 열린 초안 PR 11개, main a993373. 로컬은 새 clone으로 시작했다.
- 중간: 8개 병합 완료 head에 대해 main 조상 관계를 확인했다. 원격 보관 분기 생성 후 13개 보류 head가 8개 보관 분기에서 도달 가능한지 git merge-base --is-ancestor로 확인했다. PR 닫기와 분기 삭제 뒤 원격을 다시 조회했다.
- 완료: 브랜치 10개, 열린 PR #18 하나. main은 a993373ea694427933227f3efbf91db80ce7fe4b 그대로다. 이번 정리는 병합·배포·예약 수집 변경을 수행하지 않았다.
- 유지한 #18 코드 dc6fe58을 이 환경에서 직접 검증했다: make quality의 Ruff 위반 0건·Pyright 오류/경고 0건, make test의 194건 통과·Starlette 사용 중단 경고 1건, wheel 빌드 및 필수 소스 12개 검사 성공. Kafka/LLM은 합성 시험 범위이며 실제 브로커·유료 LLM 호출·운영 배포는 수행하지 않았다.
- 이번 커밋은 문서만 변경한다. git diff --check와 원격 최종 커밋 품질 게이트를 확인한다. 예측 성능·제품 수요·운영 인수의 미완료 상태는 바꾸지 않는다.

## 다음 작업 순서

1. #18의 CAMT 수집→초안→검토된 내부 조회 계약과 Java 프록시를 연결해 실제 조회 상태를 확인한다.
2. Kafka는 RAG 초안 작업부터 실브로커·중복 전달·재시작을 검증한다. 운영용 공유 원본 저장소와 DB 트랜잭션 아웃박스는 별도 구현 조건이다.
3. SPCX·AVGO는 각각의 자료 출처·종목 식별을 확인한 뒤 확장한다. 검색 가능 여부를 브리핑 지원 완료로 해석하지 않는다.
4. 이번 주 브리핑 흐름을 마친 뒤에만 보관 연구 중 필요한 작업을 다시 선정한다.

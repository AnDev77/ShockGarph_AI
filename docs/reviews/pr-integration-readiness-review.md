# 연구 PR 통합과 실제 실행 준비 검증

확인일: 2026-11-25 KST. 신규 기능을 추가하지 않고 기존 수집 복구 기능의 통합 가능성을 검증했다. AGENTS.md의 진행 기능 하나 유지 조건에 따라 #20을 완료·통합하기 전에 새 기능 PR을 쌓지 않는다. 이번 기록은 기존 #20에 문서로만 추가하며 원격 main 병합은 하지 않는다.

## 시작: 저장소·계획·작업 트리

세 저장소의 원격 main, 열린 PR, CI, AGENTS.md, 제품 방향과 Python/웹 일일 계획을 확인했다. Java 계획은 웹 일일 계획을 참조한다. 오래된 11/16~20 목표를 완료 실적으로 간주하지 않았다. Python main의 RAG 소유 문구는 #19에서 Java 소유로 정리할 대상이며 사용자 최신 지시대로 Python 연구만 작업했다.

| 저장소 | main | 열린 PR 생성 순서·기준 | 확인 상태 |
|---|---|---|---|
| Python | 6288f6c | #19: 11/17 06:22 UTC, feat/java-rag-ownership → main. #20: 11/18 06:48 UTC, feat/forecast-capture-coverage → main | 둘 다 초안. 각각 main과 충돌 없음. #19 head 40faea7, #20 head cb01026. #20 CI 45343142689 성공 |
| Java | b76f93a | 열린 PR 없음 | 이전 main b962053에서 갱신. 정확한 main SHA의 check-runs는 비어 있음. 이전 PR의 성공을 main CI 성공으로 대체하지 않음 |
| 웹 | 38e38b0 | #13: 11/17 00:05 UTC, feat/review-change-rationale → main | head 6316e87의 이전 CI 성공이지만 현재 main과 충돌 |

Python 작업 트리는 기존 build/dist만 미추적이었다. Java의 기존 deploy/README.md, deploy/smoke_test.py, docs/reviews/disposable-compose-acceptance-review.md 미커밋 변경을 보존했다. 웹 작업 트리는 깨끗했다.

## 중간: 실제 충돌 재현과 해결 후보

`git merge-tree --write-tree origin/feat/java-rag-ownership origin/feat/forecast-capture-coverage`는 종료 코드 1과 Review.md 충돌을 반환했다. 개별 PR의 mergeable=true가 PR 두 개를 차례대로 병합해도 충돌이 없다는 보장은 아니다.

별도 research-integration-check 작업 트리를 #19 head에서 만들고 #20을 --no-commit으로 결합했다. Review.md 공통 main 본문 뒤에 #19의 역할 변경 기록, #20의 수집 복구 기록을 모두 보존했다. 한쪽 전체를 선택하면 다른 쪽의 변경 이유·검증 기록이 사라지므로 두 추가 부분을 유지했다. 나머지 파일은 자동 병합됐고 실행 코드는 #20과 같았다. 통합 후보와 #20의 차이는 AGENTS.md, Review.md, docs/current-product-direction.md, docs/daily-work-plan.md 네 문서뿐이다.

검증 후보 tree: 15935ca504f55458517ae96aab08290ac827bab7. 이는 원격 커밋·병합·배포가 아닌 로컬 검증 대상 식별자다. 원격 main과 두 PR의 기반 브랜치는 바꾸지 않았다. 실제 병합 승인 시에는 최신 head로 이 과정을 다시 검증해야 한다.

## 완료: 시험·작업량·한계

| 검사 | 결과 |
|---|---|
| 충돌 재현 | Review.md 1개 충돌 확인 |
| 후보 충돌 처리 | 두 PR의 추가 기록 보존, 미해결 충돌 파일 0개 |
| make quality | Ruff 위반 0, Pyright 오류·경고·정보 0 |
| make test | 269개 성공, 기존 Starlette 사용 중단 경고 1개 |
| wheel 빌드·내용 | 빌드 성공, 필수 소스 14개 포함 |
| diff 검사 | 공백 오류 없음. #20 대비 실행 코드 변경 없음 |
| 원격 게이트 | 코드 head cb01026의 CI 45343142689 성공 재확인. 이번 문서 커밋의 CI는 PR 본문에 별도 기록 |

전체 시험은 날짜·출처 무결성과 사전 예측/사후 정답 분리 등을 기존 합성 시험으로 재검증했다. 두 PR의 문서를 함께 적용해도 테스트 수집·정적 분석·패키지 빌드가 깨지지 않음을 확인했다. wheel에 들어가야 하는 소스가 존재하는지도 확인했다. 이 시험은 실제 R2 수집, SMTP 수신, 두 브라우저 채팅 또는 운영 Blue/Green 전환을 재현한 것은 아니다.

작업량: 세 저장소 조사, 로컬 통합 후보 1개, 문서 충돌 1개 해결 후보, 전체 시험·빌드 재실행, 공개 리뷰 1개와 Review.md 안내 1개. 신규 제품 기능·신규 시험·모델 학습·새 PR은 없다. 이전 비공개 progress/troubleshooting/scorecard 전체는 업로드하지 않는다. 검증 기준을 읽고 안전한 시작·중간·완료 기록만 이 문서에 남긴다.

## 예약 등록과 실행 결과

[Python 수집 실행 45499964035](https://github.com/AnDev77/ShockGarph_AI/actions/runs/45499964035)은 11/24 22:20:16 UTC, 즉 11/25 07:20:16 KST에 생성됐다. main의 뉴욕 07:10 예약 설정과 실제 생성 시각은 다르다. 작업은 성공했지만 snapshot_only_preopen_gate_failed였다. 원본 readback·재고 감사·기존 공식 채점 성공과 새 사전 예측 생성 성공은 별개다. 직전 실행 45291837572와 비교해 고유 예측 거래일 증가가 없었다. 비공개 수치·원본 가격·객체 키를 전재하지 않는다.

[Java CAMT 실행 45348812180](https://github.com/AnDev77/doChallenge/actions/runs/45348812180)은 test 작업의 고정 SSM 명령·IAM 범위 검사는 성공했지만 ingest 작업은 skipped였다. `.github/workflows/camt-sec-ingest.yml`은 main에서 workflow_dispatch할 때만 ingest를 허용한다. 운영 수집이 성공했다거나 EC2 설정이 모두 준비됐다고 판단할 근거가 아니다. 실제 운영 명령은 실행하지 않았다.

## 권장 정리 순서와 판단

1. Python #19의 역할 문서 정리를 먼저 검토한다.
2. #20에 최신 main을 반영할 때 Review.md의 양쪽 기록을 유지하고 충돌을 해결한다. 동일 head의 CI와 전체 시험을 다시 확인한 뒤 승인 범위에서 병합한다.
3. main의 새 일정이 실제 실행되어 새 거래일의 예측이 원격 readback을 통과하는지 확인한다. 그 전에는 수집 병목 해결 완료로 보고하지 않는다.
4. 웹 #13은 최신 main의 Java 연결 문서와 중복 여부를 확인하고 필요한 문구만 남기거나 닫는 방향을 결정한다. 오래된 성공 CI만으로 병합하지 않는다.

이번 작업은 새로운 예측 성과를 만들지 않았다. 이미 준비된 수집 복구를 실제 main에 반영하는 결정이 우선이며, 추가 진단 기능을 계속 붙이는 것은 현재 병목을 해결하지 못한다. 성능과 제품 수요는 HOLD다. 2027 달력과 EC2 접근·TLS·SMTP·공유 MySQL/Redis·스키마 공존·운영 전환/되돌리기는 별도 미검증 조건이다. 배포·자동 병합·데이터 삭제를 수행하지 않았다.

## 2026-11-26 재확인: 이미지 배포와 학습 분기 구분

### 시작

세 main은 전날과 같은 Python 6288f6c, Java b76f93a, 웹 38e38b0다. 해당 main의 AGENTS.md·제품 방향·일일 계획도 이전 확인본과 diff가 없음을 확인했다. Java 작업 트리의 기존 미커밋 파일 3개와 웹 작업 트리를 보존했다. Python 진행 기능을 통합하기 전 다른 기능을 추가하지 않는 작업 규칙에 따라 오늘은 독립 검증과 문서 기록만 수행했다.

열린 PR 생성 순서와 상태:

- Python #19(11/17, feat/java-rag-ownership → main, head 40faea7), #20(11/18, feat/forecast-capture-coverage → main, head e756ff4): CI 성공, 개별 main 병합 가능. 함께 병합하면 Review.md 충돌이 계속 재현된다.
- Java #40(11/26 00:25 UTC, exercise/rag-asof-fetched-at → main, head 7cef562): CI 실패. 본문에서 의도적으로 SQL 바인딩을 틀리게 만든 사용자 학습용 초안이며 병합·배포 금지라고 명시한다. 제품 결함으로 자동 수정하거나 #41에 포함하지 않는다.
- Java #41(11/26 05:03 UTC, feat/immutable-image-release → main, head 7037899): 병합 가능, 일반 품질·Compose·Blue/Green·스키마 검사 성공. AWS publish/start-candidate 및 SMTP 실발송은 skipped다.
- 웹 #13(11/17, feat/review-change-rationale → main, head 6316e87): 기존 CI 성공, 현재 main과 충돌.

### 중간: 검증한 경로

Java #41을 별도 release-verification 작업 트리에 읽어 기존 변경을 건드리지 않고 `python3 -B -m unittest discover -s deploy -p test_image_release.py -v`를 실행했다. 대상은 deploy/image_release.py, deploy/test_image_release.py, deploy/image-release.md다. 이 경로는 로컬/CI에서 검사한 이미지를 ECR에 올리고 digest를 고정해 EC2가 pull하도록 한다. 그러나 운영 apply는 단일 api를 교체하며 기존 Blue/Green 전환과 별도다. 따라서 #41의 일반 Blue/Green CI 성공을 새 digest 배포 경로의 대기 버전 검사·트래픽 전환·되돌리기 검증으로 합쳐 해석하지 않는다.

### 완료와 한계

이미지 배포 계약 시험 10개가 로컬에서 통과했다. 입력·digest·revision 거부, 의존 서비스 재시작 제외, 환경 파일 보존, 실패 복귀 명령을 모의 실행으로 확인했다. 시험 출력의 published/healthy 문구는 Mock이 반환한 결과이며 실제 AWS 업로드나 서버 건강 상태가 아니다. Java 전체 시험·JAR·컨테이너 시험은 기존 정확한 head의 원격 게이트에서 확인했고 이번 로컬 실행에서 다시 수행하지 않았다. Python 실행 코드는 변경하지 않았으므로 같은 전체 시험을 로컬에서 반복하지 않았다. 문서 변경 뒤 원격 게이트는 해당 커밋으로 확인해 PR 본문에 기록한다.

작업량: 세 저장소 재조회, Java 새 PR 2건의 목적·CI 구분, 이미지 배포 계약 시험 10개, Python 병합 충돌 재확인, 문서 2개 갱신. 신규 제품 기능·새 PR·병합·배포·볼륨 삭제는 없다. Learner's High 직접 구현 변경은 없으며 버전 고정과 운영 검증 범위를 구분하는 검토만 했다.

### 실제 수집 상태와 다음 조건

[Python 예약 실행 45705961106](https://github.com/AnDev77/ShockGarph_AI/actions/runs/45705961106)은 11/25 21:36:56 UTC(11/26 06:36:56 KST)에 생성됐고 전체 작업 성공이다. 그러나 snapshot_only_preopen_gate_failed로 원본만 보관했다. readback·재고·기존 공식 채점은 성공했지만 직전 45499964035 대비 고유 예측 거래일은 늘지 않았다. 비공개 수치·원본·키는 공개하지 않는다.

현재 정리 권고는 Python #19 → #20(문서 충돌 해결·최신 main 재검증), Java #40은 사용자 학습 후 병합 없이 종료, #41은 별도 배포 기능 검토다. #41을 적용하더라도 운영 Blue/Green 성공을 주장하려면 digest 이미지를 대기 버전에 기동하고 실제 API/채팅·공유 DB/Redis·스키마 공존·트래픽 전환·실패 복구를 별도로 검증해야 한다. 이번에는 EC2 권한·TLS·SMTP·운영 데이터 상태를 확인하지 못했으며, 연구 성능과 제품 수요는 HOLD다.

# Review: CAMT 공시 수집과 검토된 브리핑 조회

## 시작과 목적

2026-11-15 KST. Python main `a993373`에서 새 브랜치를 만들었다. [웹 계획 #8](https://github.com/AnDev77/shockgraph-web/pull/8)과 [웹 구현 #9](https://github.com/AnDev77/shockgraph-web/pull/9)의 브리핑 JSON 계약을 기준으로 작업했다. 기존 포트폴리오·가격 수집 초안을 합치지 않고 자료 수집부터 조회까지 구현했다.

## 바뀐 구조와 확인할 코드

| 파일 | 역할 |
|---|---|
| [filings.py](packages/briefing/shockgraph_briefing/filings.py) | SEC 제출 목록에서 CIK·티커·수리 시각을 확인하고 CAMT 6-K/20-F 원문을 내려받는다. 고정 호스트·검증된 경로, 리다이렉트 금지, 응답 크기·형식 제한. 원문 SHA-256과 수집·수리 시각, 정제한 문단을 남긴다. |
| [pipeline.py](packages/briefing/shockgraph_briefing/pipeline.py) | 실적·전망·위험 키워드로 문단 최대 8개를 골라 구조화 요약 초안을 만든다. 검증된 수치 전용 계약이 생기기 전까지 모델 숫자 표기를 차단한다. 문단 ID와 원문 해시를 검사하고 사람이 대조한 초안의 해시로만 공개 결과를 만든다. 회사 자료 한 건이므로 방향 판단은 보류한다. |
| [명령](packages/briefing/shockgraph_briefing/__main__.py) | 수집·생성·검토 완료의 세 명령을 분리. 현재 시점에 7일 밖인 문서는 생성과 신규 공개 모두 거부한다. |
| [FastAPI](apps/briefing_api/shockgraph_briefing_api/app.py) | 내부 토큰을 요구하는 읽기 전용 조회. HTTP 요청 중 원문·LLM을 호출하지 않는다. 미검토·자료 부족·수집 실패를 구분하며, 이미 검토된 요약은 자료 날짜에 따라 이전 결과로 표시하고 30일 이후에는 더 이상 반환하지 않는다. |
| [시험](tests/unit/test_camt_briefing.py) | 미래 문서 배제, 잘못된 발행자·문서 경로·리다이렉트 거부, 초안 미노출, 인용 연결, 오래된 자료와 수집 실패 구분, 모델 불완전 응답 거부. |

흐름: **SEC 목록 → 원문 수집 → 관련 문단 선택 → 구조화 요약 초안 → 사람 검토 → FastAPI 조회**.
JSON 파일은 파일 교체 방식으로 저장하며 이번에는 로컬 파일만 사용한다. 유료 모델 호출을 켜거나 운영 네트워크를 구성하지 않았다. 웹 공개 요청은 별도 Java 프록시를 통하며 내부 토큰은 브라우저로 보낼 수 없다.

## 실행과 검토

```sh
python -m pip install -e '.[dev,viz,briefing]'
# SHOCKGRAPH_SEC_USER_AGENT에 수집 앱 이름과 운영자 연락처를 설정한다.
python -m shockgraph_briefing collect
# 사용 조건 확인 후, 서버 비밀 저장소에서 OPENAI_API_KEY와 모델명을 주입한다.
python -m shockgraph_briefing draft --allow-source-transfer
# 생성된 draft-camt.json의 각 주장과 원문을 사람이 대조한다.
python -m shockgraph_briefing publish --reviewed-sha256 <검토한-초안의-SHA256>
# BRIEFING_INTERNAL_TOKEN은 백엔드에서만 설정한다.
python -m uvicorn shockgraph_briefing_api.app:create_app --factory --host 127.0.0.1 --port 8785
```

모델 식별자는 `SHOCKGRAPH_BRIEFING_MODEL` 환경 변수로 설정한다. 허용된 출처에 대해서만 외부 모델 전송을 승인한다. 인용 ID 검사는 문장의 의미나 수치가 원문과 일치함을 자동 보증하지 않는다. 공시 본문과 실행 아티팩트는 Git에 넣지 않는다.

## 중간·완료 검증

- [SEC 공시](https://www.sec.gov/Archives/edgar/data/1109138/000117891326005000/zk2636329.htm)의 원문을 CLI로 실제 수집했다. CAMT 6-K `0001178913-26-005000`의 SEC 수리 시각은 **2026-11-04 21:03:59 KST**이고, 11/15 현재 7일 밖이다. 정제 문단 130개 중 실적과 회사 전망 관련 문단이 모두 검색되는 것을 확인했다. 초기에 단수 키워드만으로 일부 매출 문장을 놓쳐 복수형과 성장률 표현을 추가했다.
- 실제 로컬 HTTP에 웹 #9의 Zod 파서를 붙여 현재 `insufficient_sources`를 확인했다. 동일 공시를 과거 날짜로 재현한 별도 임시 데이터에서 사람이 작성·대조한 요약은 `ready/stale/withheld`와 원문 인용으로 검증했다. 과거 날짜를 재현한 시험이며 그날 수집했거나 LLM이 요약한 기록으로 계산하지 않는다.
- 로컬 Ruff·Pyright, 전체 pytest 188건, wheel 빌드와 필수 포함 파일 11개 검사 통과. 설치한 Starlette의 TestClient가 httpx 사용 중단 예정 경고를 반환했으며 실패는 없었다.
- 실제 LLM 생성은 API 키·모델 설정 부재와 7일 범위 내 공시 부재로 미실행이다. 구조화 모델 응답과 오류는 합성 응답으로 검증했다. 공개 배포, 회원 데이터 결합, 임베딩·LangGraph, MySQL 발행 저장, 독립 출처 검증 및 방향 판단은 이 단계의 완료 범위가 아니다.

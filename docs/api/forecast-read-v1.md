# 금융 위험 조회 API 계약 초안

작성일: 2026-10-27. 구현 전 계약이다. 서비스 화면과 비공개 수집·채점의 경계를 고정한다.

## 읽기 전용 요청

`GET /api/v1/assets/{symbol}/risk?horizon=5` 또는 `horizon=20`. 첫 지원 종목은 `TLT`, `SPY`다. 알 수 없는 종목·기간은 404/400으로 구분한다. 예측 계산·가격 수집·R2 비밀값 조회를 사용자 요청마다 새로 수행하지 않는다.

## 응답 상태

| status | 의미 | 화면 문구 |
|---|---|---|
| `NOT_AVAILABLE` | 감사한 실제 사전 기록이 없음 | 아직 기록된 예측이 없습니다 |
| `PENDING_OUTCOME` | 실제로 저장한 예측은 있으나 해당 기간의 미래 가격 결과가 없음 | 결과 확인 전 |
| `EVALUATED_PRIVATE` | 사후 결과가 비공개 보관됐으나 공개 승인되지 않음 | 내부 검증 중 |
| `PUBLISHED` | 데이터 권리·수치 공개 범위·평가 근거를 별도 확인한 결과만 승인 | 확인된 예측과 평가를 표시 |
| `STALE` | 마지막 완료 거래일보다 오래된 기록 | 업데이트 지연 |

200 응답의 공통 부분은 `symbol`, `horizonTradingDays`, `status`, `originSession`, `predictionAt`, `outcomeEndsAt`, `method`, `asOf`로 한정한다. 시각은 모두 UTC ISO 8601로 전송한다. 보관 index·원본 해시·계좌 정보·비밀값·가격·오차·신뢰구간은 공개하지 않는다. 본문의 실제 예상 변동성 수치는 공개 권리가 확인된 뒤에만 `forecastVolatility`로 추가하며, 확인 전에는 `null`이다. `PUBLISHED` 이전에 우수성 배지나 매수·매도 문구를 내보내지 않는다.

예시(숫자를 만든 예측이 아님):

```json
{
  "symbol": "TLT",
  "horizonTradingDays": 5,
  "status": "NOT_AVAILABLE",
  "originSession": null,
  "predictionAt": null,
  "outcomeEndsAt": null,
  "method": "PRICE_BASELINE",
  "asOf": null,
  "forecastVolatility": null
}
```

예시의 null은 조회 가능한 기록이 없는 상태를 뜻한다. 운영 API에서 실제 기록의 시각을 확보하지 못하면 해당 항목을 추정하지 않는다. `forecastVolatility`는 향후 5일의 **일별** 실현 변동성 예측이며 가격 변화율의 방향이나 수익률 예측이 아니다. 화면에는 단위를 명시한다.

## 데이터 경계와 실패

- R2 index와 원본을 읽기 감사한 뒤 종목·예측 시작일별 최초 유효 기록을 선택한다. 동일 날짜 재시도는 별개 예측으로 세지 않는다.
- 원본 읽기·해시·시각 검사 실패를 `NOT_AVAILABLE` 성공으로 숨기지 않는다. 서버 오류로 기록하고 사용자에게는 공개 가능한 일시 오류만 전달한다.
- 실제 사후 결과를 찾더라도 공개 승인 플래그가 거짓이면 `EVALUATED_PRIVATE` 상태만 보낸다. B 모델은 실제 운영 사전 기록이 생기기 전까지 `method`로 제공하지 않는다.
- 운영 저장소 연결과 서비스용 캐시/DB 메타데이터는 별도 구현 사항이며, 이 계약 문서만으로 API가 존재한다고 주장하지 않는다.

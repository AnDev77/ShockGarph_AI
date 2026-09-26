# 선행연구 지도

작성일: 2026-09-26

## 핵심 문헌과 적용 범위

| 연구 | 확인된 내용 | 본 연구에 주는 기준 |
|---|---|---|
| Wolfers & Zitzewitz (2004), *Prediction Markets* | 예측시장의 정보 집계, 확률·평균·불확실성 해석과 인과 해석의 한계를 정리 | 시장가격을 확률로 사용할 근거와 시장설계·인과 한계를 함께 제시 |
| Diercks, Katz & Wright (2026), *Kalshi and the Rise of Macro Markets* | Kalshi 거시예측을 설문·시장 내재 전망과 비교하고 실시간 분포 정보의 가치를 평가 | “Kalshi가 거시지표를 잘 맞힌다”만으로는 신규성이 부족함 |
| MacKinlay (1997), *Event Studies in Economics and Finance* | 사건 연구의 추정창·사건창·비정상수익률·검정 구조를 체계화 | 짧은 사건창과 기준수익률, 사건 독립성의 기본 틀 |
| Andersen et al. (2003), *Micro Effects of Macro Announcements* | 예정된 거시발표 주변의 고빈도 가격발견과 surprise 반응을 분석 | 일봉 `[-5,+5]` 대신 분 단위 반응과 기대 대비 surprise가 필요 |
| Giacomini & White (2006), *Tests of Conditional Predictive Ability* | 동일 관측에서 예측모형의 조건부 손실 차이를 비교하는 틀 | 사건별 대응 손실과 시간 의존성을 고려한 비교 필요 |
| BLS CPI 계절조정 문서 | 계절조정 지수는 매년 최근 5년까지 재계산될 수 있음 | 현재 다운로드 값 대신 최초 발표 빈티지 보존 필요 |

## 직접 경쟁 연구와 차별화

2026년 연준 FEDS 연구는 Kalshi가 거시 기대의 고빈도·분포형 측정치로 유용한지 직접
평가한다. 따라서 아래 주장은 피한다.

- Kalshi 거시확률을 처음 연구했다.
- 예측시장을 기존 전망과 처음 비교했다.
- 시장확률이 단순 기준보다 낮은 Brier라는 사실만으로 새로운 금융모델을 만들었다.

대신 다음 간격을 검증 대상으로 둔다.

1. 거시 결과의 확률 정확도가 **자산 수익률 분포 예측**의 개선으로 이어지는가?
2. 기존 거시 기대와 가격 상태를 통제한 뒤에도 추가 정보가 남는가?
3. 주식·장기국채·금에서 개선 방향과 실패 조건이 어떻게 다른가?
4. 유동성·스프레드·결측을 포함하면 실무에 사용 가능한 사건이 얼마나 남는가?

## 문헌별 코드·표 연결

| 문헌 개념 | 저장소 구현 또는 예정 산출물 |
|---|---|
| 적절한 확률 점수 | `score_event_probabilities`, Brier 비교표 |
| 사건 단위 독립성 | `event_order`, 월별 `event_id`, expanding-window |
| 고빈도 사건창 | 예정 `asset_window.csv`의 5분·30분 구간 |
| surprise 분리 | 예정 `release_vintage.csv`의 실제값−기대값 |
| 대응 예측 비교 | 같은 사건의 C−B CRPS와 paired bootstrap |
| 빈티지 자료 | 원본 해시와 `expectation_available_at`, `release_at` |

## 인용 후보

1. Wolfers, J., & Zitzewitz, E. (2004). Prediction Markets. *Journal of Economic
   Perspectives, 18*(2), 107–126. https://doi.org/10.1257/0895330041371321
2. Diercks, A. M., Katz, J. D., & Wright, J. H. (2026). Kalshi and the Rise of Macro
   Markets. *Finance and Economics Discussion Series 2026-010*.
   https://doi.org/10.17016/FEDS.2026.010
3. MacKinlay, A. C. (1997). Event Studies in Economics and Finance. *Journal of Economic
   Literature, 35*(1), 13–39. https://www.jstor.org/stable/2729691
4. Andersen, T. G., Bollerslev, T., Diebold, F. X., & Vega, C. (2003). Micro Effects of
   Macro Announcements: Real-Time Price Discovery in Foreign Exchange. *American Economic
   Review, 93*(1), 38–62. https://www.nber.org/papers/w8959
5. Giacomini, R., & White, H. (2006). Tests of Conditional Predictive Ability.
   *Econometrica, 74*(6), 1545–1578.
   https://www.econometricsociety.org/publications/econometrica/2006/11/01/tests-conditional-predictive-ability
6. U.S. Bureau of Labor Statistics. Seasonal Adjustment in the CPI.
   https://www.bls.gov/cpi/seasonal-adjustment/

## 문헌 검토 시 추가할 질문

- 직접 경쟁 연구가 SPY·TLT·GLD의 동일 사건 분포 예측까지 수행했는가?
- 예측시장 확률의 호가 스프레드와 무거래 문제를 어떻게 처리했는가?
- 거시발표 동시성과 정책 국면 변화를 어떤 통제 또는 하위표본으로 다뤘는가?
- 데이터·코드 공개 범위와 공급자 이용조건을 어떻게 해결했는가?

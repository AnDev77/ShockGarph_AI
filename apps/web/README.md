# 웹 분석 화면

Next.js 16과 Chakra UI v3로 만든 모바일 우선 분석 화면이다. FastAPI의 검증된 CPI 확률 연구 결과와
SPY·TLT·GLD 자산 분석 준비 상태를 조회한다. 이벤트 발생확률과 자산 수익률 추정은 서로 구분해 표시하며,
미지원·표본 부족·오류 상태에서는 예측값을 임의로 만들지 않는다.

## 로컬 실행

먼저 저장소 루트에서 FastAPI를 실행한다.

```bash
SHOCKGRAPH_RESEARCH_METADATA=artifacts/paper-dataset/<실행 ID>/metadata.json make api-dev
```

다른 터미널에서 웹 애플리케이션을 실행한다.

```bash
cd apps/web
npm ci
npm run dev
```

브라우저에서 `http://localhost:3000`을 연다. API 주소가 다르면
`NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`처럼 지정한다. API의 허용 출처는
`SHOCKGRAPH_WEB_ORIGINS`에 쉼표로 구분해 설정할 수 있다.

## 검증

```bash
npm run typecheck
npm run build
```

[제품·화면 설계](../../docs/product-ui-direction.md)의 사용자 선택, 상태 표현, 모바일 화면 원칙을 따른다.

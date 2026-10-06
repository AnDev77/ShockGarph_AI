"use client";

import { Badge, Box, Button, Flex, Grid, Heading, Spinner, Text } from "@chakra-ui/react";
import { useEffect, useState } from "react";

type AssetId = "SPY" | "TLT";
type Horizon = "m5" | "m30";
type State = "loading" | "ready" | "error";
type Finding = "raw_market_probability_outperformed_expanding_history" | "historical_frequency_had_lower_error" | "difference_not_established" | "insufficient_data";
interface Research {
  status: "ready";
  as_of: string;
  finding: Finding;
  independent_event_count: number;
  provenance: { kind: "recorded_aggregate" | "validated_snapshot"; source_document?: string; decimal_places?: number; recomputed?: boolean };
  metrics: { eligible_events: number; comparable_events: number; raw_market_brier: number; expanding_historical_brier: number; mean_brier_difference: number; paired_event_bootstrap95: [number, number] };
}
interface Comparison {
  historical_crps: number;
  kalshi_crps: number;
  mean_crps_difference: number;
  paired_event_bootstrap95: [number, number];
}
interface Analysis {
  status: "insufficient_data" | "exploratory";
  asset_id: string;
  horizon: string;
  independent_event_count: number;
  diagnostic_min_train?: number;
  diagnostic_test_events?: number;
  research_min_train?: number;
  research_test_events?: number;
  research_required_test_events?: number;
  comparison?: Comparison | null;
}
interface Market {
  status: "pending";
  probability: null;
  quote_at: null;
  release_at: null;
  contract_definition: string;
}
const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const sourceBase = "https://github.com/AnDev77/ShockGarph_AI/blob/feat/analytics/";
const findingText: Record<Finding, string> = {
  raw_market_probability_outperformed_expanding_history: "과거 표본에서 시장확률의 오차가 더 작았어요.",
  historical_frequency_had_lower_error: "과거 표본에서 과거 발생비율의 오차가 더 작았어요.",
  difference_not_established: "두 확률의 오차 차이가 아직 뚜렷하지 않아요.",
  insufficient_data: "비교할 독립 사건이 부족해요.",
};
const object = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const count = (v: unknown): v is number => finite(v) && Number.isInteger(v) && v >= 0;
const interval = (v: unknown): v is [number, number] => Array.isArray(v) && v.length === 2 && v.every(finite) && v[0] <= v[1];
function readResearch(v: unknown): Research {
  if (!object(v) || v.status !== "ready" || typeof v.as_of !== "string" || !Number.isFinite(Date.parse(v.as_of)) || typeof v.finding !== "string" || !Object.hasOwn(findingText, v.finding) || !count(v.independent_event_count) || !object(v.provenance) || !["recorded_aggregate", "validated_snapshot"].includes(String(v.provenance.kind)) || !object(v.metrics)) throw new Error("invalid research");
  const m = v.metrics;
  if (!count(m.eligible_events) || !count(m.comparable_events) || m.comparable_events !== v.independent_event_count || !finite(m.raw_market_brier) || m.raw_market_brier < 0 || m.raw_market_brier > 1 || !finite(m.expanding_historical_brier) || m.expanding_historical_brier < 0 || m.expanding_historical_brier > 1 || !finite(m.mean_brier_difference) || !interval(m.paired_event_bootstrap95)) throw new Error("invalid metrics");
  return v as unknown as Research;
}
function readAnalysis(v: unknown, asset: AssetId, horizon: Horizon): Analysis {
  if (!object(v) || !["insufficient_data", "exploratory"].includes(String(v.status)) || v.asset_id !== asset || v.horizon !== horizon || !count(v.independent_event_count)) throw new Error("invalid analysis");
  if (v.diagnostic_test_events !== undefined && (!count(v.diagnostic_min_train) || !count(v.diagnostic_test_events) || !count(v.research_min_train) || !count(v.research_test_events) || !count(v.research_required_test_events))) throw new Error("invalid counts");
  if (v.comparison != null) {
    const m = v.comparison;
    if (!object(m) || !finite(m.historical_crps) || m.historical_crps < 0 || !finite(m.kalshi_crps) || m.kalshi_crps < 0 || !finite(m.mean_crps_difference) || !interval(m.paired_event_bootstrap95)) throw new Error("invalid comparison");
  }
  return v as unknown as Analysis;
}
function readMarket(v: unknown): Market {
  if (!object(v) || v.status !== "pending" || v.probability !== null || v.quote_at !== null || v.release_at !== null || typeof v.contract_definition !== "string") throw new Error("unsupported market state");
  return v as unknown as Market;
}
async function get<T>(path: string, signal: AbortSignal, parse: (v: unknown) => T): Promise<T> {
  const res = await fetch(`${apiBase}${path}`, { signal, cache: "no-store" });
  if (!res.ok) throw new Error("API unavailable");
  return parse(await res.json());
}
const date = (value: string) => new Date(value).toLocaleDateString("ko-KR", { timeZone: "UTC", year: "numeric", month: "2-digit", day: "2-digit" });
const signed = (v: number, digits: number) => `${v > 0 ? "+" : ""}${v.toFixed(digits)}`;

interface DashboardSeed { research: Research; analysis: Analysis; market: Market }
export function Dashboard({ initialData }: { initialData?: DashboardSeed } = {}) {
  const [asset, setAsset] = useState<AssetId>("SPY");
  const [horizon, setHorizon] = useState<Horizon>("m5");
  const [refresh, setRefresh] = useState(0);
  const [research, setResearch] = useState<Research | null>(initialData?.research ?? null);
  const [analysis, setAnalysis] = useState<Analysis | null>(initialData?.analysis ?? null);
  const [market, setMarket] = useState<Market | null>(initialData?.market ?? null);
  const [researchState, setResearchState] = useState<State>(initialData ? "ready" : "loading");
  const [analysisState, setAnalysisState] = useState<State>(initialData ? "ready" : "loading");
  const [marketState, setMarketState] = useState<State>(initialData ? "ready" : "loading");
  useEffect(() => {
    const c = new AbortController();
    setResearch(null); setMarket(null); setResearchState("loading"); setMarketState("loading");
    get("/v1/research/cpi-probability", c.signal, readResearch).then(v => { if (!c.signal.aborted) { setResearch(v); setResearchState("ready"); } }).catch(() => { if (!c.signal.aborted) setResearchState("error"); });
    get("/v1/market-expectations/cpi", c.signal, readMarket).then(v => { if (!c.signal.aborted) { setMarket(v); setMarketState("ready"); } }).catch(() => { if (!c.signal.aborted) setMarketState("error"); });
    return () => c.abort();
  }, [refresh]);
  useEffect(() => {
    const c = new AbortController();
    setAnalysis(null); setAnalysisState("loading");
    const params = new URLSearchParams({ asset_id: asset, event_category: "CPI", horizon });
    get(`/v1/analysis?${params}`, c.signal, v => readAnalysis(v, asset, horizon)).then(v => { if (!c.signal.aborted) { setAnalysis(v); setAnalysisState("ready"); } }).catch(() => { if (!c.signal.aborted) setAnalysisState("error"); });
    return () => c.abort();
  }, [asset, horizon, refresh]);
  const m = research?.metrics;
  const comparison = analysis?.comparison;
  const busy = [researchState, analysisState, marketState].includes("loading");
  const improvement = comparison && comparison.mean_crps_difference < 0 && comparison.paired_event_bootstrap95[1] < 0;
  const sampleNote = analysis?.diagnostic_test_events !== undefined
    ? `초기 학습 ${analysis.diagnostic_min_train}건의 탐색 시험은 ${analysis.diagnostic_test_events}건. 초기 학습 ${analysis.research_min_train}건의 주요 시험은 ${analysis.research_test_events}/${analysis.research_required_test_events}건으로, 표본 게이트와 추가 검증을 함께 확인해요.`
    : "독립 사건 수와 Bootstrap 구간을 함께 확인해요. 보고서가 연결되면 탐색 평가와 주요 평가의 시험 표본을 구분해 보여드려요.";

  return (
    <Box className="app-shell">
      <a className="skip-link" href="#overview">본문으로 이동</a>
      <Box as="aside" className="sidebar">
        <a href="#overview" className="brand"><span className="brand-mark"><Icon name="pulse" /></span>shockgraph<span className="brand-dot">.</span></a>
        <div className="workspace-label">YOUR EVENT WORKSPACE</div>
        <nav aria-label="주요 메뉴" className="side-nav">
          <a href="#overview" className="nav-primary"><Icon name="grid" /> 대시보드 <span className="nav-count">01</span></a>
          <a href="#asset-impact"><Icon name="chart" /> 자산 분석</a>
          <a href="#market-brief"><Icon name="news" /> 시장 브리핑</a>
          <a href="#research-notes"><Icon name="book" /> 연구 노트</a>
        </nav>
        <div className="sidebar-note"><span className="small-kicker">A LITTLE MORE CLARITY</span><p>시장의 기대와<br />자산의 반응 사이.</p><span>숫자의 의미를 함께 읽어보세요.</span><a href="#research-notes">평가 기준 알아보기 <Icon name="arrow" /></a></div>
        <div className="sidebar-bottom"><span className="status-dot" /> Research preview <span>v0.1</span></div>
      </Box>
      <Box className="main-shell">
        <Flex as="header" className="topbar" justify="space-between" align="center">
          <Text className="breadcrumb">워크스페이스 <span>/</span> <strong>대시보드</strong></Text>
          <Flex align="center" gap="12px"><span className="header-chip">과거 평가 모드</span><span className="avatar" aria-label="ShockGraph 연구 공간">SG</span></Flex>
        </Flex>
        <Box as="main" className="main-content" id="overview">
          <Flex className="page-heading" justify="space-between" align="center" gap="20px">
            <Box><Text className="eyebrow">EXPECTATIONS → ASSET IMPACT</Text><Heading as="h1">시장의 기대를, 내 자산의 관점으로.</Heading><Text className="page-description">CPI 시장확률과 ETF 반응, 두 가지 이야기를 한눈에 확인하세요.</Text></Box>
            <Button className="refresh-button" variant="outline" onClick={() => setRefresh(v => v + 1)} disabled={busy}><Icon name="refresh" />{busy ? "불러오는 중" : "새로고침"}</Button>
          </Flex>
          <Grid className="stat-grid">
            <Stat icon="pulse" label="CPI 확률 비교" value={research ? `${research.independent_event_count}` : "—"} unit={research ? "독립 사건" : ""} detail={research ? `${date(research.as_of)} 기준 · 과거 평가` : researchState === "loading" ? "평가 기록을 불러오고 있어요" : "평가 기록 연결 필요"} tone="purple" />
            <Stat icon="chart" label="ETF 분석 범위" value="SPY · TLT" detail="미국 주식 · 장기 국채 / 사용자 선택" tone="peach" />
            <Stat icon="layers" label="자산 반응 시험" value={analysis?.diagnostic_test_events !== undefined ? `${analysis.diagnostic_test_events}` : "—"} unit={analysis?.diagnostic_test_events !== undefined ? "독립 사건" : ""} detail={analysis?.diagnostic_test_events !== undefined ? `공통 사건 ${analysis.independent_event_count}건 · 탐색 평가` : "평가 보고서 연결 필요"} tone="lime" />
          </Grid>
          <Grid className="upper-grid">
            <Box as="section" className="panel cpi-panel" aria-labelledby="cpi-title">
              <Flex justify="space-between" align="start" gap="12px"><Box><Text className="section-kicker">01 / EVENT PROBABILITY</Text><Heading as="h2" id="cpi-title">CPI 예측, 얼마나 잘 맞았을까?</Heading></Box><Badge className="soft-badge">과거 예비 평가</Badge></Flex>
              <Text className="panel-description">CPI 전월비가 0.3%를 초과할 확률 · Brier 점수가 낮을수록 정확</Text>
              {researchState === "loading" && <Loading />}
              {researchState === "error" && <Empty title="평가 기록을 연결해 주세요" body="기존 보고서를 불러오지 못했어요. API 실행 후 새로고침해 주세요." />}
              {research && m && <>
                <ScoreBars first={{ label: "과거 발생비율", value: m.expanding_historical_brier }} second={{ label: "Kalshi 시장확률", value: m.raw_market_brier }} digits={4} />
                <div className="cpi-result"><span className="result-icon"><Icon name="arrow" /></span><div><strong>{findingText[research.finding]}</strong><p>손실 차이 {signed(m.mean_brier_difference, 4)} · 95% 구간 [{m.paired_event_bootstrap95.map(v => v.toFixed(4)).join(", ")}]</p></div></div>
                <div className="provenance-line">{research.provenance.kind === "recorded_aggregate" ? "기존 연구 문서의 소수 4자리 집계 · 재계산 아님" : "연결된 연구 스냅샷"}<a href="#research-notes">해석 기준 <Icon name="arrow" /></a></div>
              </>}
            </Box>
            <Box as="section" className="market-panel" id="market-brief" aria-labelledby="market-title">
              <Flex justify="space-between" align="center"><span className="market-kicker"><span className="status-dot" /> MARKET BRIEF</span><Icon name="news" /></Flex>
              <Heading as="h2" id="market-title">다음 CPI,<br />시장은 어떻게 보고 있을까?</Heading>
              <div className="market-number">—<span>현재 확률</span></div>
              <div className="market-divider" />
              {marketState === "loading" ? <Loading /> : <><span className="pending-tag">{market ? "현재 호가 연결 대기" : "브리핑 연결 확인 필요"}</span><Text className="market-description">{market ? "CPI 계약의 현재 호가가 연결되면 시장 기대를 짧은 브리핑으로 보여드려요." : "브리핑 상태를 불러오지 못했어요. API 연결 후 새로고침해 주세요."}</Text></>}
              <Text className="market-footnote">과거 평가 점수는 현재의 CPI 발생확률이 아닙니다.</Text>
            </Box>
          </Grid>
          <Box as="section" className="panel asset-panel" id="asset-impact" aria-labelledby="asset-title">
            <Flex className="asset-header" justify="space-between" align="start" gap="16px"><Box><Text className="section-kicker">02 / ASSET IMPACT</Text><Heading as="h2" id="asset-title">그래서, 내 관심 자산에는?</Heading><Text className="panel-description">같은 사건에서 과거 발생비율과 Kalshi 확률을 넣은 수익률 모델을 비교했어요.</Text></Box><div className="asset-controls"><div role="group" aria-label="관심 자산" className="segmented">{(["SPY", "TLT"] as AssetId[]).map(v => <Button key={v} className={asset === v ? "segment selected" : "segment"} aria-pressed={asset === v} onClick={() => setAsset(v)}>{v}</Button>)}</div><div role="group" aria-label="발표 후 관측 구간" className="segmented">{(["m5", "m30"] as Horizon[]).map(v => <Button key={v} className={horizon === v ? "segment selected" : "segment"} aria-pressed={horizon === v} onClick={() => setHorizon(v)}>{v === "m5" ? "5분" : "30분"}</Button>)}</div></div></Flex>
            <div className="asset-body" aria-live="polite" aria-busy={analysisState === "loading"}>
              <div className="asset-comparison"><div className="selected-asset"><span className={asset === "SPY" ? "ticker-icon spy" : "ticker-icon tlt"}>{asset === "SPY" ? "S" : "T"}</span><div><strong>{asset} <span>{asset === "SPY" ? "미국 주식" : "장기 국채"}</span></strong><p>발표 후 {horizon === "m5" ? "5분" : "30분"} · 수익률 분포 오차 (CRPS)</p></div><span className="chart-hint">낮을수록 좋음</span></div>
                {analysisState === "loading" ? <Loading /> : analysisState === "error" ? <Empty title="분석 연결을 확인해 주세요" body="선택한 자산의 보고서를 불러오지 못했어요." /> : comparison ? <ScoreBars first={{ label: "과거 발생비율 모델", value: comparison.historical_crps }} second={{ label: "Kalshi 확률 추가 모델", value: comparison.kalshi_crps }} digits={6} /> : <Empty title="평가 보고서 연결 대기" body="표본이 확인된 보고서가 연결되면 실제 비교 수치를 보여드려요." />}
                {comparison && <Text className="asset-ci">오차 차이 {signed(comparison.mean_crps_difference, 6)} · 95% 구간 [{comparison.paired_event_bootstrap95.map(v => v.toFixed(6)).join(", ")}]</Text>}
              </div>
              <div className="asset-verdict"><span className="verdict-label">WHAT THIS MEANS</span><Heading as="h3">{comparison ? improvement ? "탐색 표본에서\n추가 효과가 관찰됐어요." : "자산 예측의 추가 효과는\n아직 확인되지 않았어요." : "연결된 평가로\n확인할 수 있어요."}</Heading><Text>{comparison ? "현재 결과는 과거 발생비율 기준선과의 탐색 비교입니다. 상승·하락 예측이나 투자수익으로 해석할 수 없어요." : "과거 평가와 현재 자산 예측을 구분해 제공해요."}</Text><div className="sample-gate"><span>주요 평가용 시험 표본</span><strong>{analysis?.research_test_events !== undefined ? `${analysis.research_test_events} / ${analysis.research_required_test_events}건` : "연결 대기"}</strong>{analysis?.research_test_events !== undefined && <div className="gate-track"><span style={{ width: `${Math.min(100, 100 * analysis.research_test_events / Math.max(1, analysis.research_required_test_events ?? 1))}%` }} /></div>}</div></div>
            </div>
          </Box>
          <Box as="section" className="research-notes" id="research-notes" aria-labelledby="notes-title">
            <Flex justify="space-between" align="center"><Heading as="h2" id="notes-title">숫자 너머의 연구 노트</Heading><span className="notes-caption">판단에 필요한 세 가지 기준</span></Flex>
            <Grid className="notes-grid"><Note number="01" title="CPI 정확도 ≠ 자산 예측력" body="Brier는 CPI 계약의 YES/NO를, CRPS는 ETF 수익률 분포를 평가해요. 두 평가의 사건 수가 같아도 같은 사건 집합을 뜻하지 않아요." path="docs/cpi-coverage-review.md" /><Note number="02" title="표본 수와 불확실성을 함께" body={sampleNote} path="docs/paper/results/cpi-kalshi-ablation-2026-09-30.json" /><Note number="03" title="현재는 과거 평가 모드" body="현재 호가, 다음 발표시각, 미래 수익률은 연결 전까지 표시하지 않아요. 실제 데이터가 있는 결과부터 공개해요." path="docs/reviews/market-expectation-dashboard-review.md" /></Grid>
          </Box>
          <footer className="page-footer"><span>ShockGraph AI · 시장 기대와 자산 반응 연구</span><span>과거 평가 화면 · 자동 주문 기능 없음</span></footer>
        </Box>
      </Box>
    </Box>
  );
}
function Loading() { return <Flex className="loading-state" align="center" justify="center" gap="9px" role="status"><Spinner size="sm" /> 기록을 불러오는 중</Flex>; }
function Empty({ title, body }: { title: string; body: string }) { return <div className="empty-state" role="status"><strong>{title}</strong><p>{body}</p></div>; }
function Stat({ icon, label, value, unit, detail, tone }: { icon: string; label: string; value: string; unit?: string; detail: string; tone: string }) { return <div className="stat-card"><Flex justify="space-between" align="center"><span className="stat-label">{label}</span><span className={`stat-icon ${tone}`}><Icon name={icon} /></span></Flex><div className="stat-value">{value}<span>{unit}</span></div><p>{detail}</p></div>; }
function ScoreBars({ first, second, digits }: { first: { label: string; value: number }; second: { label: string; value: number }; digits: number }) {
  const max = Math.max(first.value, second.value);
  return <div className="score-bars">{[first, second].map((v, i) => <div className="score-row" key={v.label}><div className="score-heading"><span><i className={i === 0 ? "legend history" : "legend kalshi"} />{v.label}</span><strong>{v.value.toFixed(digits)}</strong></div><div className="score-track" aria-hidden="true"><div className={i === 0 ? "score-fill history" : "score-fill kalshi"} style={{ width: `${max > 0 ? v.value / max * 100 : 0}%` }} /></div></div>)}</div>;
}
function Note({ number, title, body, path }: { number: string; title: string; body: string; path: string }) { return <a className="note-card" href={`${sourceBase}${path}`} target="_blank" rel="noreferrer"><span className="note-number">{number}</span><strong>{title}</strong><p>{body}</p><span className="note-link">근거 기록 보기 <Icon name="arrow" /></span></a>; }
function Icon({ name }: { name: string }) {
  const paths: Record<string, React.ReactNode> = {
    pulse: <path d="M3 13h4l3-8 4 14 3-8h4" />,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    chart: <><path d="M4 4v16h16M8 15l4-5 4 2 4-6" /></>,
    news: <><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M7 8h10M7 12h4M7 16h4M15 12h2M15 16h2" /></>,
    book: <><path d="M12 5v15M12 5C9 3 5 3 3 4v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-2-1-6-1-9 1Z" /></>,
    arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
    refresh: <><path d="M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-1l2 6M4 12l2 6a7 7 0 0 0 12-1" /></>,
    layers: <><path d="m12 3 10 5-10 5L2 8l10-5Zm-10 9 10 5 10-5M2 16l10 5 10-5" /></>,
  };
  return <svg data-icon={name} width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] ?? paths.chart}</svg>;
}

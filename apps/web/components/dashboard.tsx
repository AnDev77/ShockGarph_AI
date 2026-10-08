"use client";

import { Box, Button, Flex, Grid, Heading, Spinner, Text } from "@chakra-ui/react";
import { useEffect, useState } from "react";
import { readPortfolioReport, type PortfolioReply, type Source, type Horizon, type Quantiles } from "./portfolio-contract";

export interface DashboardSeed { portfolio: PortfolioReply }
const labels = { above: "컨센서스 상회", inline: "컨센서스 부합", below: "컨센서스 하회" };
const percent = (v: number) => `${v > 0 ? "+" : ""}${(v * 100).toFixed(2)}%`;
const probability = (v: number) => `${(v * 100).toFixed(1)}%`;
const usd = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const date = (v: string) => new Date(v).toLocaleDateString("ko-KR", { timeZone: "UTC", year: "numeric", month: "2-digit", day: "2-digit" });
const utc = (v: string) => `${date(v)} ${new Date(v).toISOString().slice(11, 16)} UTC`;

export function Dashboard({ initialData, initialSource = "demo", initialHorizon = "m30", initialSpyPercent = 60, initialValuation = 10000 }: { initialData?: DashboardSeed; initialSource?: Source; initialHorizon?: Horizon; initialSpyPercent?: number; initialValuation?: number | null } = {}) {
  const [source, setSource] = useState<Source>(initialSource);
  const [horizon, setHorizon] = useState<Horizon>(initialHorizon);
  const [spyInput, setSpyInput] = useState(String(initialSpyPercent));
  const [valuationInput, setValuationInput] = useState(initialValuation === null ? "" : String(initialValuation));
  const spyPercent = Number(spyInput);
  const valuation = valuationInput.trim() === "" ? null : Number(valuationInput);
  const valid = spyInput.trim() !== "" && Number.isInteger(spyPercent) && spyPercent >= 0 && spyPercent <= 100 && (valuation === null || Number.isFinite(valuation) && valuation >= 0 && valuation <= 1e12);
  const key = `${source}:${horizon}:${spyPercent}:${valuation}`;
  const [reply, setReply] = useState<PortfolioReply | null>(initialData?.portfolio ?? null);
  const [loadedKey, setLoadedKey] = useState(initialData ? key : "");
  const [state, setState] = useState<"loading" | "ready" | "error">(initialData ? "ready" : "loading");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); let cancelled = false;
    setReply(null); setLoadedKey(""); setState("loading");
    if (!valid) return () => controller.abort();
    let timeout: ReturnType<typeof setTimeout>;
    const debounce = setTimeout(async () => {
      timeout = setTimeout(() => controller.abort(), 8000);
      try {
        const params = new URLSearchParams({ source, horizon, spy_weight: String(spyPercent / 100), tlt_weight: String((100 - spyPercent) / 100) });
        if (valuation !== null) params.set("portfolio_value", String(valuation));
        const response = await fetch(`/api/v1/portfolios/cpi?${params}`, { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw new Error("API unavailable");
        const data = readPortfolioReport(await response.json(), { source, horizon, spyPercent, valuation });
        if (!cancelled) { setReply(data); setLoadedKey(key); setState("ready"); }
      } catch { if (!cancelled) setState("error"); }
      finally { clearTimeout(timeout); }
    }, 250);
    return () => { cancelled = true; clearTimeout(debounce); clearTimeout(timeout); controller.abort(); };
  }, [key, valid, source, horizon, spyPercent, valuation, refresh]);
  const current = valid && loadedKey === key ? reply : null;
  const report = current && current.status !== "pending" ? current : null;
  const result = report?.status === "ready" ? report.result : null;
  const q = result?.quantiles;
  const domain: [number, number] = [Math.min(-0.005, q?.q10 ?? 0) - 0.002, Math.max(0.005, q?.q90 ?? 0) + 0.002];
  const minutes = horizon === "m5" ? "5분" : "30분";
  return <Box className="app-shell">
    <a className="skip-link" href="#overview">본문으로 이동</a>
    <Box as="aside" className="sidebar">
      <a href="/" className="brand"><span className="brand-mark"><Icon name="pulse" /></span>shockgraph<span className="brand-dot">.</span></a>
      <div className="workspace-label">YOUR PORTFOLIO WORKSPACE</div>
      <nav className="side-nav" aria-label="주요 메뉴"><a href="/" className="nav-primary"><Icon name="grid" /> 내 포트폴리오</a><a href="#portfolio-result"><Icon name="chart" /> 이벤트 영향</a><a href="/methodology"><Icon name="book" /> 연구 노트</a></nav>
      <div className="sidebar-note"><span className="small-kicker">BEFORE THE NEXT EVENT</span><p>경제 뉴스의 의미를,<br />내 자산의 관점으로.</p><span>시장 기대와 과거 반응으로 변화 가능성을 살펴보세요.</span><a href="/methodology">분석 방법 알아보기 <Icon name="arrow" /></a></div>
      <div className="sidebar-bottom"><span className="status-dot" /> Portfolio simulator <span>v0.3</span></div>
    </Box>
    <Box className="main-shell">
      <Flex as="header" className="topbar" justify="space-between" align="center"><Text className="breadcrumb">워크스페이스 <span>/</span> <strong>내 포트폴리오 영향</strong></Text><a className="header-chip" href="/methodology">연구 노트 ↗</a></Flex>
      <Box as="main" className="main-content scenario-content" id="overview">
        <Flex className="page-heading" justify="space-between" align="center" gap="20px"><Box><Text className="eyebrow">MARKET EXPECTATIONS / MY PORTFOLIO</Text><Heading as="h1">이번 경제 발표,<br />내 자산은 얼마나 움직일까?</Heading><Text className="page-description">내 비중에 맞춘 상승·하락 가능성과 변화 범위를 한눈에 확인하세요.</Text></Box><Button className="refresh-button" onClick={() => setRefresh(v => v + 1)} disabled={state === "loading"}><Icon name="refresh" />새로고침</Button></Flex>
        <Flex className="scenario-toolbar" justify="space-between" align="center" gap="12px"><div className="segmented" role="group" aria-label="데이터 모드">{(["demo", "actual"] as Source[]).map(v => <Button key={v} data-source={v} className={`segment ${source === v ? "selected" : ""}`} aria-pressed={source === v} onClick={() => setSource(v)}>{v === "demo" ? "데모 살펴보기" : "실제 데이터"}</Button>)}</div><span className={`source-tag ${source}`} data-testid="source-label">{source === "demo" ? "합성 데이터 · 실제 시장값 아님" : "실제 데이터 연결 상태"}</span></Flex>
        <div className={`data-notice ${source}`} role="note">{source === "demo" ? "합성 사건과 합성 호가로 계산하는 체험용 시뮬레이터입니다. 표시된 변화율·확률은 실제 금융 예측 성과가 아닙니다." : "이용권과 시점 정합성이 확인된 사건별 자료가 연결된 경우에만 실제 추정치를 표시합니다."}</div>
        <Grid className="portfolio-top-grid">
          <Box as="section" className="panel portfolio-input-panel"><Text className="section-kicker">01 / MY ALLOCATION</Text><Heading as="h2">내 자산 구성</Heading><Text className="panel-description">미국 주식과 장기 국채의 비중을 설정하세요.</Text>
            <div className="allocation-row"><label htmlFor="spy-weight"><span className="ticker-icon spy">S</span> SPY <small>미국 주식</small></label><div><input id="spy-weight" type="number" min="0" max="100" step="1" value={spyInput} onChange={e => setSpyInput(e.target.value)} aria-describedby="allocation-help" /><span>%</span></div></div>
            <input className="allocation-slider" type="range" min="0" max="100" step="1" value={valid ? spyPercent : 0} onChange={e => setSpyInput(e.target.value)} aria-label="SPY 비중 조절" />
            <div className="allocation-row"><span><span className="ticker-icon tlt">T</span> TLT <small>장기 국채</small></span><strong>{valid ? 100 - spyPercent : "—"}%</strong></div>
            <p id="allocation-help" className="allocation-help">TLT는 남은 비중으로 계산합니다. 합계 100% · USD 기준.</p>
            <div className="allocation-presets" role="group" aria-label="예시 포트폴리오 비중">{[0, 25, 50, 60, 75, 100].map(v => <button type="button" key={v} data-spy-weight={v} aria-pressed={valid && spyPercent === v} className={valid && spyPercent === v ? "active" : ""} onClick={() => setSpyInput(String(v))}>{v}/{100 - v}</button>)}</div>
            <label htmlFor="portfolio-value" className="valuation-label">포트폴리오 평가액 <span>선택 · USD</span></label><div className="valuation-field"><span>$</span><input id="portfolio-value" type="number" min="0" max="1000000000000" step="any" placeholder="입력하면 금액 변화를 표시합니다" value={valuationInput} onChange={e => setValuationInput(e.target.value)} /></div>
            {!valid && <p className="input-error" role="alert">SPY 비중은 0–100의 정수, 평가액은 0–1조 달러 범위로 입력해 주세요.</p>}
          </Box>
          <Box as="section" className="market-panel portfolio-event-panel"><span className="market-kicker">02 / EVENT TO WATCH</span><Heading as="h2">CPI · 미국 소비자물가</Heading><Text className="market-description">선택한 발표가 내 포트폴리오에 미칠 단기 영향을 추정합니다.</Text><div className="event-options"><span className="active">CPI</span><span>FOMC · 준비 중</span><span>원유재고 · 준비 중</span></div><div className="segmented" role="group" aria-label="발표 후 관측 구간">{(["m5", "m30"] as Horizon[]).map(v => <Button key={v} data-horizon={v} className={`segment ${horizon === v ? "selected" : ""}`} aria-pressed={horizon === v} onClick={() => setHorizon(v)}>{v === "m5" ? "발표 후 5분" : "발표 후 30분"}</Button>)}</div><div className="market-divider" />{report ? <dl><dt>자료 기준시각{source === "demo" ? " (합성)" : ""}</dt><dd>{utc(report.as_of)}</dd><dt>분석 대상 발표{source === "demo" ? " (합성)" : ""}</dt><dd>{utc(report.release_at)}</dd></dl> : <p className="market-description">자료가 준비되면 분석 기준시각과 대상 발표를 함께 표시합니다.</p>}</Box>
        </Grid>
        <section id="portfolio-result" aria-live="polite" aria-busy={valid && !current && state !== "error"}>
          <div className="scenario-distribution-heading"><Text className="section-kicker">03 / PORTFOLIO IMPACT</Text><Heading as="h2">내 포트폴리오의 예상 변화</Heading><Text className="panel-description">CPI 발표 후 {minutes} · 시장 기대와 과거 공동 반응을 결합한 모형 추정</Text></div>
          {!valid ? <div className="scenario-state">비중과 평가액을 확인하면 결과를 계산합니다.</div> : !current && state !== "error" ? <div className="scenario-state" role="status"><Spinner size="sm" /> 내 비중으로 계산하는 중</div> : state === "error" ? <div className="scenario-state" role="alert"><strong>분석 연결을 확인해 주세요.</strong><p>응답을 가져오지 못했거나 계산 결과 검증을 통과하지 못했습니다.</p><Button className="refresh-button" onClick={() => setRefresh(v => v + 1)}>다시 시도</Button></div> : current?.status === "pending" ? <div className="scenario-state actual-pending" role="status"><Icon name="layers" /><Heading as="h3">실제 포트폴리오 자료 연결 대기</Heading><Text>발표 전 기대 자료와 같은 사건의 SPY·TLT 수익률이 필요합니다. 기존 연구 점수만으로 변화 범위를 복원할 수 없습니다.</Text><Text>실제 추정치를 준비하기 전에는 합성 숫자로 대체하지 않습니다.</Text><Button data-source="demo" className="refresh-button" onClick={() => setSource("demo")}>합성 데모로 흐름 확인</Button></div> : report?.status === "insufficient_data" ? <div className="scenario-state" role="status"><Heading as="h3">계산에 필요한 사건 표본이 부족합니다.</Heading><Text>확률이 있는 시나리오마다 {report.minimum_sample_count}개 이상의 사건이 필요합니다. 누락된 시나리오를 제외하지 않고 전체 추정을 보류합니다.</Text></div> : report && result && q ? <>
            <Grid className="portfolio-metrics"><Box className="panel portfolio-metric"><Text>평균 예상 변화</Text><strong className={result.expected_return < 0 ? "negative" : "positive"}>{percent(result.expected_return)}</strong><span>{result.expected_change_usd === null ? "평가액을 입력하면 금액도 표시합니다" : `${usd(result.expected_change_usd)} · 입력한 평가액 기준`}</span></Box><Box className="panel portfolio-metric"><Text>상승 추정확률</Text><strong>{probability(result.probability_up)}</strong><span>수익률이 0보다 클 가능성</span></Box><Box className="panel portfolio-metric"><Text>하락 추정확률</Text><strong>{probability(result.probability_down)}</strong><span>보합 {probability(result.probability_flat)} · 반올림 표시</span></Box></Grid>
            <Box className="panel portfolio-range"><Flex align="center" justify="space-between" gap="16px" wrap="wrap"><Box><Text className="section-kicker">ESTIMATED RANGE / P10–P90</Text><Heading as="h3">{percent(q.q10)} <span>~</span> {percent(q.q90)}</Heading><Text className="panel-description">{result.amount_range_usd ? `${usd(result.amount_range_usd[0])} ~ ${usd(result.amount_range_usd[1])} · ` : ""}모형 분포의 중앙 80% 범위 · 실제 보장률은 미검증</Text></Box><span className="sample-pill">고유 사건 {report.total_event_count}개</span></Flex><QuantilePlot quantiles={q} domain={domain} asset="포트폴리오" /><div className="quantile-legend"><span><i className="legend kalshi" /> P25–P75</span><span>세로선: 중앙값 {percent(q.q50)}</span></div><div className="distribution-provenance">{date(report.period_start)} – {date(report.period_end)}<span>{source === "demo" ? "합성 사건 · 예측 성과 아님" : "과거 사건 · 예측 성능 미입증"}</span></div></Box>
            <Grid className="scenario-asset-grid">{report.assets.map(asset => <Box className="panel portfolio-asset-summary" key={asset.asset_id}><Flex align="center" gap="12px"><span className={`ticker-icon ${asset.asset_id.toLowerCase()}`}>{asset.asset_id === "SPY" ? "S" : "T"}</span><Heading as="h3">{asset.asset_id}</Heading><span className="sample-pill">비중 {probability(asset.weight)}</span></Flex><div className="asset-summary-values"><span>자산 평균 변화 <strong>{percent(asset.expected_return)}</strong></span><span>포트폴리오 평균에 기여 <strong>{percent(asset.return_contribution)}</strong></span></div></Box>)}</Grid>
          </> : null}
        </section>
        {report && <details className="panel portfolio-method"><summary>시장 기대와 계산 근거 펼쳐보기 <span>시나리오 · 과거 표본</span></summary><p>비교 기준 CPI 전월비 {report.consensus_mom.toFixed(1)}%. 아래는 컨센서스 대비 시나리오 확률이며, 물가가 전월보다 오를 확률과 다릅니다.</p><div className="portfolio-scenarios">{report.scenarios.map(row => <div key={row.scenario}><span>{labels[row.scenario]}</span><strong>{probability(row.implied_probability)}</strong><small>과거 사건 {row.sample_count}개</small></div>)}</div><p>같은 사건의 SPY·TLT 수익률에 내 비중을 적용한 뒤, 시나리오 확률로 분포를 혼합합니다. 과거와 현재의 경제 상황이 다를 수 있습니다. 사건 수는 통계적 충분성을 보장하지 않습니다.</p><a href="/methodology">연구 기록과 검증 한계 확인 ↗</a></details>}
        <div className="interpretation-card"><Icon name="book" /><div><strong>결과는 시장 기대와 과거 반응에 기반한 추정입니다.</strong><p>수익률 범위는 손실 한도나 수익 보장이 아닙니다. 실제 결과가 범위를 벗어날 수 있으며, 장기 자산 가격과 매수·매도 시점을 예측하지 않습니다.</p></div><a href="/methodology">방법론 보기 ↗</a></div>
        <footer className="page-footer"><span>ShockGraph AI · 거시경제 이벤트 기반 포트폴리오 리스크 시뮬레이터</span><a href="/methodology">연구 노트 · 검증 기록 ↗</a></footer>
      </Box>
    </Box>
  </Box>;
}

function QuantilePlot({ quantiles: q, domain: [low, high], asset }: { quantiles: Quantiles; domain: [number, number]; asset: string }) {
  const x = (n: number) => 28 + (n - low) / (high - low) * 404;
  return <svg className="quantile-plot" viewBox="0 0 460 110" role="img" aria-label={`${asset} 과거 수익률 P10 ${percent(q.q10)}, 중앙값 ${percent(q.q50)}, P90 ${percent(q.q90)}`}>
    <line x1={28} x2={432} y1={80} y2={80} stroke="#e6e8ee" />
    {[low, (low + high) / 2, high].map(n => <g key={n}><line x1={x(n)} x2={x(n)} y1={80} y2={85} stroke="#bdc0cc" /><text x={x(n)} y={102} textAnchor="middle" fill="#8c90a0" fontSize="11">{percent(n)}</text></g>)}
    <line x1={x(0)} x2={x(0)} y1={12} y2={80} stroke="#c0c2ce" strokeDasharray="3 4" /><text x={x(0)} y={10} textAnchor="middle" fill="#9396a4" fontSize="10">0%</text>
    <line x1={x(q.q10)} x2={x(q.q90)} y1={45} y2={45} stroke="#8c7ced" strokeWidth="2" />
    {[q.q10, q.q90].map((n, i) => <line key={i} x1={x(n)} x2={x(n)} y1={34} y2={56} stroke="#8c7ced" strokeWidth="2" />)}
    <rect x={x(q.q25)} y={28} width={Math.max(0, x(q.q75) - x(q.q25))} height={34} rx={6} fill="#e5dfff" stroke="#b7a9f1" /><line x1={x(q.q50)} x2={x(q.q50)} y1={25} y2={65} stroke="#5d50e8" strokeWidth="3" />
  </svg>;
}

function Icon({ name }: { name: string }) {
  const paths: Record<string, React.ReactNode> = {
    pulse: <path d="M3 13h4l3-8 4 14 3-8h4" />,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    chart: <path d="M4 4v16h16M8 15l4-5 4 2 4-6" />,
    book: <path d="M12 5v15M12 5C9 3 5 3 3 4v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-2-1-6-1-9 1Z" />,
    arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
    refresh: <path d="M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-1l2 6M4 12l2 6a7 7 0 0 0 12-1" />,
    layers: <path d="m12 3 10 5-10 5L2 8l10-5Zm-10 9 10 5 10-5M2 16l10 5 10-5" />,
  };
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] ?? paths.chart}</svg>;
}

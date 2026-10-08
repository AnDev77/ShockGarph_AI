export type Source = "demo" | "actual";
export type Horizon = "m5" | "m30";
export type Quantiles = { q10: number; q25: number; q50: number; q75: number; q90: number };
export interface ScenarioRow {
  scenario: "above" | "inline" | "below"; implied_probability: number; sample_count: number;
  status: "ready" | "insufficient_data"; quantiles: Quantiles | null;
}
export interface PortfolioResult {
  expected_return: number; probability_up: number; probability_down: number; probability_flat: number;
  quantiles: Quantiles; expected_change_usd: number | null; amount_range_usd: [number, number] | null;
}
export interface PortfolioReport {
  schema_version: "cpi-portfolio-report-v1"; status: "ready" | "insufficient_data";
  horizon: Horizon; weights: { SPY: number; TLT: number }; portfolio_value_usd: number | null;
  as_of: string; release_at: string; consensus_mom: number; currency: "USD";
  minimum_sample_count: number; total_event_count: number; period_start: string; period_end: string;
  interpretation: "market_weighted_historical_joint_distribution"; performance_status: "not_established";
  provenance: { source_kind: "synthetic" | "licensed_historical"; dataset_sha256: string };
  unavailable_probability_mass: number; scenarios: ScenarioRow[]; result: PortfolioResult | null;
  assets: { asset_id: "SPY" | "TLT"; weight: number; expected_return: number; return_contribution: number }[];
}
export type PortfolioReply = PortfolioReport | {
  schema_version: "cpi-portfolio-report-v1"; status: "pending"; reason: string;
  horizon: Horizon; weights: { SPY: number; TLT: number }; result: null; assets: []; scenarios: [];
};
export interface RequestContext { source: Source; horizon: Horizon; spyPercent: number; valuation: number | null }
const object = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const probability = (v: unknown): v is number => finite(v) && v >= 0 && v <= 1;
const count = (v: unknown): v is number => finite(v) && Number.isInteger(v) && v >= 0;
const time = (v: unknown): v is string => typeof v === "string" && Number.isFinite(Date.parse(v));
const near = (a: number, b: number) => Math.abs(a - b) < 1e-9;
const validQuantiles = (v: unknown) => {
  if (!object(v)) return false;
  const values = [v.q10, v.q25, v.q50, v.q75, v.q90];
  return values.every(finite) && values.every((n, i) => n >= -1 && (!i || n >= values[i - 1]));
};

export function readPortfolioReport(value: unknown, context: RequestContext): PortfolioReply {
  if (!object(value) || value.schema_version !== "cpi-portfolio-report-v1" || value.horizon !== context.horizon || !object(value.weights) || value.weights.SPY !== context.spyPercent / 100 || value.weights.TLT !== (100 - context.spyPercent) / 100) throw new Error("mismatched portfolio");
  if (value.status === "pending") {
    if (typeof value.reason !== "string" || value.result !== null || !Array.isArray(value.assets) || value.assets.length || !Array.isArray(value.scenarios) || value.scenarios.length || "provenance" in value) throw new Error("invalid pending state");
    return value as PortfolioReply;
  }
  if (!["ready", "insufficient_data"].includes(value.status as string) || value.currency !== "USD" || value.portfolio_value_usd !== context.valuation || value.interpretation !== "market_weighted_historical_joint_distribution" || value.performance_status !== "not_established" || !object(value.provenance) || value.provenance.source_kind !== (context.source === "demo" ? "synthetic" : "licensed_historical") || typeof value.provenance.dataset_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(value.provenance.dataset_sha256) || !time(value.as_of) || !time(value.release_at) || Date.parse(value.as_of) >= Date.parse(value.release_at) || !finite(value.consensus_mom) || !count(value.minimum_sample_count) || value.minimum_sample_count < 2 || !count(value.total_event_count) || !Array.isArray(value.scenarios) || value.scenarios.length !== 3 || !probability(value.unavailable_probability_mass) || !Array.isArray(value.assets)) throw new Error("invalid report");
  if (value.total_event_count > 0 && (!time(value.period_start) || !time(value.period_end) || Date.parse(value.period_start) > Date.parse(value.period_end) || Date.parse(value.period_end) >= Date.parse(value.as_of))) throw new Error("invalid history period");
  let sum = 0, samples = 0, missing = 0; const seen = new Set();
  for (const row of value.scenarios) {
    if (!object(row) || !["above", "inline", "below"].includes(row.scenario as string) || seen.has(row.scenario) || !probability(row.implied_probability) || !count(row.sample_count)) throw new Error("invalid scenario");
    seen.add(row.scenario); sum += row.implied_probability; samples += row.sample_count;
    if (row.sample_count < value.minimum_sample_count) {
      missing += row.implied_probability;
      if (row.status !== "insufficient_data" || row.quantiles !== null) throw new Error("invalid sample state");
    } else if (row.status !== "ready" || !validQuantiles(row.quantiles)) throw new Error("invalid scenario quantiles");
  }
  if (!near(sum, 1) || samples !== value.total_event_count || !near(missing, value.unavailable_probability_mass)) throw new Error("inconsistent scenario mixture");
  if (value.status === "insufficient_data") {
    if (missing <= 0 || value.result !== null || value.assets.length) throw new Error("invalid withheld result");
  } else {
    const r = value.result;
    if (missing > 0 || !object(r) || !finite(r.expected_return) || r.expected_return < -1 || !validQuantiles(r.quantiles) || !probability(r.probability_up) || !probability(r.probability_down) || !probability(r.probability_flat) || !near(r.probability_up + r.probability_down + r.probability_flat, 1) || value.assets.length !== 2) throw new Error("invalid result");
    if (context.valuation === null) {
      if (r.expected_change_usd !== null || r.amount_range_usd !== null) throw new Error("unexpected valuation");
    } else if (!finite(r.expected_change_usd) || !near(r.expected_change_usd, r.expected_return * context.valuation) || !Array.isArray(r.amount_range_usd) || r.amount_range_usd.length !== 2 || !r.amount_range_usd.every(finite) || !object(r.quantiles) || !finite(r.quantiles.q10) || !finite(r.quantiles.q90) || !near(r.amount_range_usd[0], r.quantiles.q10 * context.valuation) || !near(r.amount_range_usd[1], r.quantiles.q90 * context.valuation)) throw new Error("invalid amounts");
    let contribution = 0; const assets = new Set();
    for (const asset of value.assets) {
      if (!object(asset) || !["SPY", "TLT"].includes(asset.asset_id as string) || assets.has(asset.asset_id) || asset.weight !== value.weights[asset.asset_id as string] || !finite(asset.expected_return) || asset.expected_return < -1 || !finite(asset.return_contribution) || !finite(asset.weight) || !near(asset.return_contribution, asset.weight * asset.expected_return)) throw new Error("invalid asset contribution");
      assets.add(asset.asset_id); contribution += asset.return_contribution;
    }
    if (!near(contribution, r.expected_return)) throw new Error("inconsistent mean");
  }
  return value as unknown as PortfolioReport;
}

import { NextRequest, NextResponse } from "next/server";

const allowed = new Set([
  "v1/data-readiness/cpi", "v1/portfolios/cpi", "v1/scenarios/cpi", "v1/research/cpi-probability", "v1/research/cpi-kalshi-ablation",
  "v1/analysis", "v1/market-expectations/cpi", "health/ready",
]);

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const path = (await context.params).path.join("/");
  if (!allowed.has(path)) return NextResponse.json({ error: "unsupported_endpoint" }, { status: 404 });
  const base = process.env.SHOCKGRAPH_API_URL ?? (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000" : "");
  if (!base) return NextResponse.json({ error: "api_not_configured" }, { status: 503 });
  try {
    const url = new URL(base);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash || url.pathname !== "/") throw new Error("invalid base");
    url.pathname = `/${path}`;
    url.search = request.nextUrl.search;
    const response = await fetch(url, { signal: AbortSignal.timeout(6000), cache: "no-store" });
    const data: unknown = await response.json();
    return NextResponse.json(data, { status: response.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ error: "upstream_unavailable" }, { status: 503 });
  }
}

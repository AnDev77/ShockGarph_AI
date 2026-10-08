"""외부 요청 없이 기존 보고서를 API 경계로 읽어 화면 리뷰용 JSON을 출력한다."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from shockgraph_api.app import create_app


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    client = TestClient(
        create_app(
            service_mode="demo",
            recorded_summary_path=(
                root / "docs/paper/results/cpi-probability-recorded-2026-09-26.json"
            ),
            ablation_report_path=root / "docs/paper/results/cpi-kalshi-ablation-2026-09-30.json",
        )
    )
    endpoints = {
        "research": "/v1/research/cpi-probability",
        "analysis": "/v1/analysis?asset_id=SPY&event_category=CPI&horizon=m5",
        "market": "/v1/market-expectations/cpi",
        "report": "/v1/research/cpi-kalshi-ablation",
    }
    data = {}
    for key, endpoint in endpoints.items():
        response = client.get(endpoint)
        response.raise_for_status()
        data[key] = response.json()
    views = {}
    for source in ("demo", "actual"):
        views[source] = {}
        for horizon in ("m5", "m30"):
            views[source][horizon] = {}
            for asset in ("SPY", "TLT"):
                result = client.get("/v1/scenarios/cpi", params={
                    "source": source, "horizon": horizon, "asset_id": asset
                })
                result.raise_for_status()
                views[source][horizon][asset.lower()] = result.json()
    data["scenario_views"] = views
    portfolios = {}
    for source in ("demo", "actual"):
        portfolios[source] = {}
        for horizon in ("m5", "m30"):
            portfolios[source][horizon] = {}
            for share in (0, 25, 50, 60, 75, 100):
                response = client.get("/v1/portfolios/cpi", params={
                    "source": source, "horizon": horizon,
                    "spy_weight": share / 100, "tlt_weight": (100 - share) / 100,
                    "portfolio_value": 10000,
                })
                response.raise_for_status()
                portfolios[source][horizon][str(share)] = {"portfolio": response.json()}
    data["portfolio_views"] = portfolios
    print(json.dumps(data, ensure_ascii=False))


if __name__ == "__main__":
    main()

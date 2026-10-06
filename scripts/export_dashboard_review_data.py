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
    print(json.dumps(data, ensure_ascii=False))


if __name__ == "__main__":
    main()

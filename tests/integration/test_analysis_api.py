from __future__ import annotations

import json

from fastapi.testclient import TestClient
from shockgraph_api.app import create_app


def _write_research_metadata(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "paper-event-v1",
                "series_ticker": "KXCPI",
                "event_count": 55,
                "source_checked_at": "2026-09-26T09:49:00+00:00",
                "event_probability_comparison": {
                    "eligible_events": 29,
                    "comparable_events": 24,
                    "raw_market_brier": 0.1005,
                    "expanding_historical_brier": 0.2342,
                    "mean_brier_difference": -0.1337,
                    "paired_event_bootstrap95": [-0.1876, -0.0857],
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_api_distinguishes_verified_probability_result_from_missing_asset_result(tmp_path) -> None:
    client = TestClient(create_app(research_metadata_path=_write_research_metadata(tmp_path)))

    assert client.get("/health/live").json() == {"status": "live"}
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"

    research = client.get("/v1/research/cpi-probability").json()
    assert research["status"] == "ready"
    assert research["independent_event_count"] == 24
    assert research["metrics"]["raw_market_brier"] == 0.1005

    assets = client.get("/v1/assets").json()
    assert {row["asset_id"] for row in assets["items"]} == {"SPY", "TLT", "GLD"}
    assert all(row["status"] == "insufficient_data" for row in assets["items"])

    analysis = client.get(
        "/v1/analysis", params={"asset_id": "SPY", "event_category": "CPI", "horizon": "m5"}
    )
    assert analysis.status_code == 200
    assert analysis.json()["status"] == "insufficient_data"
    assert analysis.json()["reason"] == "asset_price_dataset_not_loaded"
    assert "expected_return" not in analysis.json()


def test_api_rejects_unsupported_combinations_and_fails_readiness_without_snapshot() -> None:
    client = TestClient(create_app())
    assert client.get("/health/ready").status_code == 503
    assert client.get("/v1/research/cpi-probability").status_code == 503
    unsupported = client.get(
        "/v1/analysis", params={"asset_id": "QQQ", "event_category": "CPI", "horizon": "m5"}
    )
    assert unsupported.status_code == 404
    assert unsupported.json()["detail"]["status"] == "unsupported"


def test_api_rejects_unverified_research_schema(tmp_path) -> None:
    path = tmp_path / "metadata.json"
    path.write_text('{"schema_version":"unknown"}', encoding="utf-8")
    client = TestClient(create_app(research_metadata_path=path))
    assert client.get("/health/ready").status_code == 503
    assert client.get("/health/ready").json()["reason"] == "invalid_research_snapshot"

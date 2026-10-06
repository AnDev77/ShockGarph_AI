from __future__ import annotations

import json

import pytest
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
    assert research["finding"] == "raw_market_probability_outperformed_expanding_history"

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


def test_api_allows_local_web_origin(tmp_path) -> None:
    client = TestClient(create_app(research_metadata_path=_write_research_metadata(tmp_path)))

    response = client.get(
        "/v1/assets",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_api_rejects_unverified_research_schema(tmp_path) -> None:
    path = tmp_path / "metadata.json"
    path.write_text('{"schema_version":"unknown"}', encoding="utf-8")
    client = TestClient(create_app(research_metadata_path=path))
    assert client.get("/health/ready").status_code == 503
    assert client.get("/health/ready").json()["reason"] == "invalid_research_snapshot"


@pytest.mark.parametrize(
    ("market", "difference", "interval", "finding"),
    [
        (0.3, 0.0658, [0.01, 0.12], "historical_frequency_had_lower_error"),
        (0.2, -0.0342, [-0.1, 0.02], "difference_not_established"),
        (0.2342, 0, [-0.02, 0.02], "difference_not_established"),
    ],
)
def test_probability_finding_follows_metrics_not_a_fixed_success_message(
    tmp_path, market, difference, interval, finding
) -> None:
    path = _write_research_metadata(tmp_path)
    payload = json.loads(path.read_text())
    metrics = payload["event_probability_comparison"]
    metrics.update(
        raw_market_brier=market,
        mean_brier_difference=difference,
        paired_event_bootstrap95=interval,
    )
    path.write_text(json.dumps(payload))
    client = TestClient(create_app(research_metadata_path=path))
    assert client.get("/v1/research/cpi-probability").json()["finding"] == finding


def test_recorded_review_serves_existing_aggregates_without_current_quotes() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    client = TestClient(
        create_app(
            recorded_summary_path=(
                root / "docs/paper/results/cpi-probability-recorded-2026-09-26.json"
            ),
            ablation_report_path=root / "docs/paper/results/cpi-kalshi-ablation-2026-09-30.json",
        )
    )
    assert client.get("/health/ready").status_code == 200
    result = client.get("/v1/research/cpi-probability").json()
    assert result["provenance"]["kind"] == "recorded_aggregate"
    assert result["provenance"]["decimal_places"] == 4
    assert result["provenance"]["recomputed"] is False
    assert result["metrics"]["raw_market_brier"] == 0.1005
    assert result["as_of"] == "2026-09-26"
    for asset in ("SPY", "TLT"):
        for horizon in ("m5", "m30"):
            analysis = client.get(
                "/v1/analysis",
                params={"asset_id": asset, "event_category": "CPI", "horizon": horizon},
            ).json()
            assert analysis["diagnostic_test_events"] == 19
            assert analysis["research_test_events"] == 4
            assert analysis["comparison"]["mean_crps_difference"] > 0
    current = client.get("/v1/market-expectations/cpi").json()
    assert current["status"] == "pending"
    assert current["probability"] is None
    assert current["quote_at"] is None
    assert current["release_at"] is None


@pytest.mark.parametrize("invalid", ["nan", "reversed_interval", "inconsistent_difference"])
def test_probability_snapshot_rejects_invalid_metrics(tmp_path, invalid) -> None:
    path = _write_research_metadata(tmp_path)
    payload = json.loads(path.read_text())
    metrics = payload["event_probability_comparison"]
    if invalid == "nan":
        metrics["mean_brier_difference"] = float("nan")
    elif invalid == "reversed_interval":
        metrics["paired_event_bootstrap95"] = [-0.0857, -0.1876]
    else:
        metrics["mean_brier_difference"] = -0.5
    path.write_text(json.dumps(payload))
    client = TestClient(create_app(research_metadata_path=path))
    assert client.get("/v1/research/cpi-probability").status_code == 503

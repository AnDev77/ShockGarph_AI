from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from shockgraph_collector.client import KalshiPublicClient
from shockgraph_data_pipeline.raw_store import ImmutableRawStore

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_kalshi_cpi_curve import audit_event_curve, parse_threshold_market  # noqa: E402
from export_cpi_curve_summary import summarize_curve_report  # noqa: E402


def test_event_curve_fetches_every_threshold_and_builds_distribution(tmp_path) -> None:
    as_of = datetime(2026, 10, 14, 12, 25, tzinfo=UTC)
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path.endswith("/historical/markets"):
            return httpx.Response(
                200,
                json={
                    "markets": [
                        {
                            "ticker": "KXCPI-26SEP-T0.2",
                            "event_ticker": "KXCPI-26SEP",
                            "floor_strike": 0.2,
                            "functional_strike": "greater",
                        }
                    ],
                    "cursor": "",
                },
            )
        if request.url.path.endswith("/markets"):
            return httpx.Response(
                200,
                json={
                    "markets": [
                        {
                            "ticker": "KXCPI-26SEP-T0.3",
                            "event_ticker": "KXCPI-26SEP",
                            "floor_strike": 0.3,
                            "functional_strike": "greater_than",
                        },
                        {
                            "ticker": "KXCPI-26SEP-T0.4",
                            "event_ticker": "KXCPI-26SEP",
                            "floor_strike": 0.5,
                        },
                    ],
                    "cursor": "",
                },
            )
        probability = 0.78 if "T0.2" in request.url.path else 0.53
        return httpx.Response(
            200,
            json={
                "candlesticks": [
                    {
                        "end_period_ts": int((as_of - timedelta(minutes=1)).timestamp()),
                        "yes_bid": {"close_dollars": str(probability - 0.01)},
                        "yes_ask": {"close_dollars": str(probability + 0.01)},
                        "volume_fp": "3",
                    }
                ]
            },
        )

    with KalshiPublicClient(transport=httpx.MockTransport(handler)) as client:
        report = audit_event_curve(
            client,
            ImmutableRawStore(tmp_path),
            event_ticker="KXCPI-26SEP",
            as_of=as_of,
            request_interval_seconds=0,
        )

    assert report["status"] == "eligible"
    assert report["candidate_threshold_markets"] == 2
    assert report["market_rejection_counts"] == {"floor_strike_mismatch": 1}
    assert report["quote_status_counts"] == {"eligible": 2}
    assert report["distribution"]["thresholds"] == [0.2, 0.3]
    assert report["distribution"]["probabilities_above"] == pytest.approx([0.78, 0.53])
    assert report["distribution"]["bin_probabilities"] == pytest.approx([0.22, 0.25, 0.53])
    assert any("/historical/markets/KXCPI-26SEP-T0.2/candlesticks" in p for p in requests)
    assert any("/series/KXCPI/markets/KXCPI-26SEP-T0.3/candlesticks" in p for p in requests)
    assert len(list(tmp_path.rglob("*.json"))) == 4

    summary = summarize_curve_report(report)
    assert summary["curve"]["threshold_count"] == 2
    assert summary["curve"]["raw_monotone"] is True
    assert "quotes" not in summary
    assert "probabilities_above" not in str(summary)


def test_market_parser_requires_matching_directional_contract() -> None:
    market = {
        "ticker": "KXCPI-26SEP-T0.3",
        "event_ticker": "KXCPI-26SEP",
        "floor_strike": 0.3,
        "functional_strike": "less",
    }
    assert parse_threshold_market(market, "KXCPI-26SEP") == (None, "unsupported_relation")
    assert parse_threshold_market(market, "KXCPI-26AUG") == (None, "event_mismatch")

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from shockgraph_collector.client import KalshiPublicClient
from shockgraph_data_pipeline.raw_store import ImmutableRawStore

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_kalshi_cpi import audit_cpi, score_event_probabilities  # noqa: E402


def test_audit_uses_correct_candle_tier_and_reports_quality(tmp_path) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        paths.append(path)
        market = {
            "ticker": "KXCPI-26AUG-T0.3",
            "event_ticker": "KXCPI-26AUG",
            "close_time": "2026-09-11T12:25:00Z",
            "result": "yes",
        }
        if path.endswith("/historical/markets"):
            return httpx.Response(200, json={"markets": [], "cursor": ""})
        if path.endswith("/markets"):
            return httpx.Response(200, json={"markets": [market], "cursor": ""})
        if path.endswith("/candlesticks"):
            return httpx.Response(
                200,
                json={
                    "candlesticks": [
                        {
                            "end_period_ts": 1789129440,
                            "yes_bid": {"close_dollars": "0.40"},
                            "yes_ask": {"close_dollars": "0.43"},
                            "volume_fp": "2",
                        }
                    ]
                },
            )
        raise AssertionError(path)

    with KalshiPublicClient(transport=httpx.MockTransport(handler)) as client:
        report = audit_cpi(
            client,
            ImmutableRawStore(tmp_path),
            request_interval_seconds=0,
        )
    assert report["settled_fixed_threshold_events"] == 1
    assert report["schema_version"] == "kalshi-cpi-audit-v2"
    assert report["status_counts"]["eligible"] == 1
    assert report["event_probability_comparison"]["eligible_events"] == 1
    assert (
        report["event_probability_comparison"]["raw_market_brier_all_eligible"] == (0.415 - 1) ** 2
    )
    assert any("/series/KXCPI/markets/" in path for path in paths)
    assert len(list(tmp_path.rglob("*.json"))) == 3


def test_probability_score_uses_only_prior_settlements_for_baseline() -> None:
    events: list[dict[str, Any]] = [
        {
            "market_ticker": f"KXCPI-{index}-T0.3",
            "outcome": "yes" if index % 2 == 0 else "no",
            "status": "no_eligible_candles",
        }
        for index in range(10)
    ]
    events.extend(
        [
            {
                "market_ticker": "KXCPI-10-T0.3",
                "outcome": "yes",
                "status": "eligible",
                "probability_yes": 0.8,
            },
            {
                "market_ticker": "KXCPI-11-T0.3",
                "outcome": "no",
                "status": "eligible",
                "probability_yes": 0.2,
            },
        ]
    )
    result = score_event_probabilities(events, min_history=10)
    assert result["eligible_events"] == 2
    assert result["comparable_events"] == 2
    assert result["raw_market_brier"] == pytest.approx(0.04)
    assert result["comparisons"][0]["outcome_binary"] == 1
    assert result["comparisons"][0]["probability_yes"] == pytest.approx(0.8)
    assert result["comparisons"][0]["expanding_historical_probability"] == pytest.approx(0.5)
    assert result["comparisons"][0]["expanding_historical_loss"] == pytest.approx(0.25)
    assert result["comparisons"][1]["expanding_historical_loss"] == pytest.approx((6 / 11) ** 2)

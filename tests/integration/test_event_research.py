from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from probe_cpi_coverage import (  # noqa: E402
    inspect_pre_release_candles,
    inventory,
    sample_pre_release,
)
from shockgraph_collector.client import KalshiPublicClient  # noqa: E402


def test_research_cli_replays_identically_and_preserves_input(tmp_path) -> None:
    source = ROOT / "data/fixtures/analytics/synthetic_cpi.json"
    before = source.read_bytes()
    command = [
        sys.executable,
        str(ROOT / "scripts/run_event_research.py"),
        "--input",
        str(source),
        "--output",
        str(tmp_path),
        "--min-train",
        "4",
    ]
    first = json.loads(subprocess.check_output(command, text=True))
    second = json.loads(subprocess.check_output(command, text=True))
    assert first == second
    report = json.loads(Path(first["report"]).read_text())
    assert report["status"] == "synthetic_only"
    assert report["evaluated_events"] == 8
    assert report["promotion_status"] == "not_evaluated"
    assert source.read_bytes() == before
    assert len(list(tmp_path.rglob("report.json"))) == 1


def test_inventory_deduplicates_and_marks_page_limit_partial() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params.get("cursor"))
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "markets": [
                    {"ticker": "CPI-contract", "event_ticker": "KXCPI-TEST", "result": "yes"}
                ],
                "cursor": "next" if not request.url.params.get("cursor") else "",
            },
        )

    with KalshiPublicClient(transport=httpx.MockTransport(handler)) as client:
        partial = inventory(client, "/historical/markets", max_pages=1)
        complete = inventory(client, "/historical/markets", max_pages=2)
    assert partial["status"] == "partial"
    assert complete["complete"]
    assert complete["observed_resolved_events"] == 1
    assert complete["observed_contracts"] == 1
    assert seen == [None, None, "next"]


def test_inventory_rejects_repeated_cursor() -> None:
    with (
        KalshiPublicClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"markets": [], "cursor": "repeat"})
            )
        ) as client,
        pytest.raises(ValueError, match="repeated cursor"),
    ):
        inventory(client, "/markets", max_pages=3)


def test_inventory_accepts_legacy_cpi_event_ticker() -> None:
    with KalshiPublicClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "markets": [
                        {"ticker": "CPI-22OCT-T0.3", "event_ticker": "CPI-22OCT", "result": "yes"}
                    ],
                    "cursor": "",
                },
            )
        )
    ) as client:
        result = inventory(client, "/historical/markets", max_pages=1)
    assert result["observed_resolved_events"] == 1


def test_cpi_candle_gate_rejects_late_and_untradable_prices() -> None:
    prediction = datetime(2026, 9, 11, 12, 25, tzinfo=UTC)
    ts = int(prediction.timestamp())
    rows = [
        {
            "end_period_ts": ts - 60,
            "yes_bid": {"close_dollars": "0.41"},
            "yes_ask": {"close_dollars": "0.43"},
            "volume_fp": "2.00",
        },
        {
            "end_period_ts": ts + 60,
            "yes_bid": {"close_dollars": "0.45"},
            "yes_ask": {"close_dollars": "0.47"},
            "volume_fp": "4.00",
        },
        {
            "end_period_ts": ts - 120,
            "yes_bid": {"close_dollars": "0.50"},
            "yes_ask": {"close_dollars": "0.49"},
            "volume_fp": "1.00",
        },
        {
            "end_period_ts": ts - 180,
            "yes_bid": {"close_dollars": "0.39"},
            "yes_ask": {"close_dollars": "0.42"},
            "volume_fp": "0.00",
        },
    ]
    outcome = inspect_pre_release_candles({"candlesticks": rows}, prediction)
    assert outcome["candidate_candles"] == 4
    assert outcome["eligible_candles"] == 1
    assert outcome["near_release_candles"] == 1
    assert outcome["latest_eligible_end_at"] == datetime.fromtimestamp(ts - 60, UTC).isoformat()
    assert outcome["latest_quote"] == {
        "end_at": datetime.fromtimestamp(ts - 60, UTC).isoformat(),
        "yes_midpoint": pytest.approx(0.42),
        "spread": pytest.approx(0.02),
        "volume": pytest.approx(2),
    }


def test_old_candle_and_ex_post_volume_do_not_choose_a_favorable_contract() -> None:
    release = datetime(2026, 9, 11, 12, 30, tzinfo=UTC)
    old = int((release - timedelta(minutes=55)).timestamp())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/historical/markets"):
            return httpx.Response(
                200,
                json={
                    "markets": [
                        {
                            "ticker": "KXCPI-26AUG-T0.1",
                            "event_ticker": "KXCPI-26AUG",
                            "result": "no",
                            "volume_fp": "1",
                        },
                        {
                            "ticker": "KXCPI-26AUG-T0.3",
                            "event_ticker": "KXCPI-26AUG",
                            "result": "yes",
                            "volume_fp": "999999",
                        },
                    ],
                    "cursor": "",
                },
            )
        if request.url.path.endswith("/markets"):
            return httpx.Response(200, json={"markets": [], "cursor": ""})
        return httpx.Response(
            200,
            json={
                "candlesticks": [
                    {
                        "end_period_ts": old,
                        "yes_bid": {"close_dollars": "0.40"},
                        "yes_ask": {"close_dollars": "0.43"},
                        "volume_fp": "3",
                    },
                ]
            },
        )

    with KalshiPublicClient(transport=httpx.MockTransport(handler)) as client:
        result = sample_pre_release(client, event_ticker="KXCPI-26AUG", release_at=release)
    assert result["ticker"] == "KXCPI-26AUG-T0.1"
    assert result["status"] == "stale_candles"
    assert result["near_release_candles"] == 0


def test_bounded_sample_checks_a_real_market_ticker_without_using_settlement_price() -> None:
    release = datetime(2026, 9, 11, 12, 30, tzinfo=UTC)
    selected = "KXCPI-26AUG-T0.3"
    queried = []

    def handler(request: httpx.Request) -> httpx.Response:
        queried.append((request.url.path, dict(request.url.params)))
        if request.url.path.endswith("/historical/markets"):
            return httpx.Response(
                200,
                json={
                    "markets": [
                        {
                            "ticker": selected,
                            "event_ticker": "KXCPI-26AUG",
                            "result": "yes",
                            "volume_fp": "100.00",
                        }
                    ],
                    "cursor": "",
                },
            )
        if request.url.path.endswith("/markets"):
            return httpx.Response(200, json={"markets": [], "cursor": ""})
        if request.url.path.endswith("/candlesticks"):
            return httpx.Response(
                200,
                json={
                    "candlesticks": [
                        {
                            "end_period_ts": int((release - timedelta(minutes=6)).timestamp()),
                            "yes_bid": {"close_dollars": "0.4"},
                            "yes_ask": {"close_dollars": "0.5"},
                            "volume_fp": "2",
                        }
                    ]
                },
            )
        raise AssertionError("unexpected path")

    with KalshiPublicClient(transport=httpx.MockTransport(handler)) as client:
        result = sample_pre_release(client, event_ticker="KXCPI-26AUG", release_at=release)
    assert result["status"] == "eligible"
    assert result["ticker"] == selected
    assert result["eligible_candles"] == 1
    assert queried[-1][1]["end_ts"] == str(int((release - timedelta(minutes=5)).timestamp()))


def test_cpi_sample_rejects_unverified_event_identifier() -> None:
    with (
        KalshiPublicClient(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client,
        pytest.raises(ValueError, match="CPI event ticker"),
    ):
        sample_pre_release(client, event_ticker="../../secret", release_at=datetime.now(UTC))

from __future__ import annotations

import json
from pathlib import Path

import pytest
from shockgraph_data_pipeline.kalshi_contract import (
    ContractViolation,
    iter_market_snapshots,
    market_probability,
    payload_sha256,
    validate_candlesticks,
)

FIXTURES = Path(__file__).parents[2] / "data" / "fixtures" / "kalshi"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_event_fixture_yields_normalized_market_snapshot() -> None:
    snapshots = list(iter_market_snapshots(load_fixture("events_response.json")))

    assert len(snapshots) == 1
    assert snapshots[0].ticker == "KXCPI-26SEP-T0.3"
    assert snapshots[0].observed_probability == pytest.approx(0.42)
    assert snapshots[0].observed_at.tzinfo is not None


def test_reversed_yes_quote_is_rejected() -> None:
    market = load_fixture("events_response.json")["events"][0]["markets"][0]
    market["yes_bid_dollars"] = "0.7000"
    market["yes_ask_dollars"] = "0.6000"

    with pytest.raises(ContractViolation, match="yes bid exceeds yes ask"):
        market_probability(market)


def test_payload_hash_is_key_order_independent() -> None:
    left = {"event": "KXCPI", "probability": 0.42}
    right = {"probability": 0.42, "event": "KXCPI"}

    assert payload_sha256(left) == payload_sha256(right)
    assert len(payload_sha256(left)) == 64


def test_candlesticks_are_monotonic_and_probabilities_are_bounded() -> None:
    candles = validate_candlesticks(load_fixture("candlesticks_response.json"))

    assert len(candles) == 2
    assert candles[0].end_period < candles[1].end_period
    assert all(0.0 <= candle.close_probability <= 1.0 for candle in candles)


def test_settled_market_result_is_binary() -> None:
    payload = load_fixture("historical_market_response.json")
    payload["market"]["result"] = "maybe"

    with pytest.raises(ContractViolation, match="result"):
        list(iter_market_snapshots({"events": [{"markets": [payload["market"]]}]}))


from __future__ import annotations

from datetime import UTC, datetime

import pytest
from shockgraph_collector.alpaca import normalize_alpaca_minute_bars

RAW_HASH = "a" * 64


def test_alpaca_bar_start_is_normalized_to_close_availability_time() -> None:
    bars = normalize_alpaca_minute_bars(
        {
            "bars": {
                "SPY": [
                    {
                        "t": "2026-03-11T12:28:00Z",
                        "o": 100,
                        "h": 101,
                        "l": 99,
                        "c": 100.5,
                        "v": 10,
                    }
                ]
            },
            "next_page_token": None,
        },
        raw_hash=RAW_HASH,
    )

    assert len(bars) == 1
    assert bars[0].price_at == datetime(2026, 3, 11, 12, 29, tzinfo=UTC)
    assert bars[0].available_at == bars[0].price_at
    assert bars[0].extended_hours is True
    assert bars[0].close == pytest.approx(100.5)


def test_alpaca_regular_session_bar_is_not_marked_extended_hours() -> None:
    bars = normalize_alpaca_minute_bars(
        {
            "bars": {
                "TLT": [
                    {
                        "t": "2026-03-11T13:30:00Z",
                        "o": 90,
                        "h": 91,
                        "l": 89,
                        "c": 90.5,
                        "v": 20,
                    }
                ]
            }
        },
        raw_hash=RAW_HASH,
    )

    assert bars[0].price_at == datetime(2026, 3, 11, 13, 31, tzinfo=UTC)
    assert bars[0].extended_hours is False


def test_alpaca_normalizer_rejects_unknown_symbol_and_malformed_rows() -> None:
    with pytest.raises(ValueError, match="unsupported Alpaca symbol"):
        normalize_alpaca_minute_bars(
            {"bars": {"QQQ": []}},
            raw_hash=RAW_HASH,
        )
    with pytest.raises(ValueError, match="bar row"):
        normalize_alpaca_minute_bars(
            {"bars": {"SPY": ["bad"]}},
            raw_hash=RAW_HASH,
        )

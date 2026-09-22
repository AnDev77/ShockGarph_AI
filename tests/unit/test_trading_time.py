from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from shockgraph_data_pipeline.trading_time import (
    latest_at_or_before,
    require_trading_day,
    trading_session_date,
)


def test_utc_timestamp_maps_to_each_venue_local_session() -> None:
    instant = datetime(2026, 9, 21, 23, 30, tzinfo=UTC)

    assert trading_session_date(instant, venue="XNYS") == date(2026, 9, 21)
    assert trading_session_date(instant, venue="XKRX") == date(2026, 9, 22)


def test_weekend_and_configured_holiday_are_not_trading_days() -> None:
    with pytest.raises(ValueError, match="not a trading day"):
        require_trading_day(date(2026, 9, 20))
    with pytest.raises(ValueError, match="not a trading day"):
        require_trading_day(date(2026, 9, 21), holidays=[date(2026, 9, 21)])


def test_as_of_alignment_never_selects_future_observation() -> None:
    rows = [
        {"observed_at": datetime(2026, 9, 21, 19, tzinfo=UTC), "close": 100},
        {"observed_at": datetime(2026, 9, 21, 20, tzinfo=UTC), "close": 101},
        {"observed_at": datetime(2026, 9, 21, 21, tzinfo=UTC), "close": 999},
    ]

    selected = latest_at_or_before(
        rows,
        feature_as_of=datetime(2026, 9, 21, 20, 30, tzinfo=UTC),
        timestamp=lambda row: row["observed_at"],
    )

    assert selected["close"] == 101

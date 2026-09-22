from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError
from shockgraph_domain.records import (
    AssetPriceRecord,
    EventRecord,
    MarketSnapshotRecord,
    OrderBookSnapshotRecord,
)


def utc(hour: int = 0) -> datetime:
    return datetime(2026, 9, 17, hour, tzinfo=UTC)


def test_event_record_requires_ordered_utc_timestamps() -> None:
    event = EventRecord(
        source="kalshi",
        external_event_id="KXCPI-26SEP",
        title="CPI in September 2026",
        category="us_cpi",
        open_time=utc(1),
        close_time=utc(2),
        status="open",
        created_at=utc(),
        updated_at=utc(),
    )

    assert event.open_time.tzinfo is UTC


def test_non_utc_timestamp_is_rejected() -> None:
    kst = timezone(timedelta(hours=9))

    with pytest.raises(ValidationError, match="UTC"):
        EventRecord(
            source="kalshi",
            external_event_id="KXCPI-26SEP",
            title="CPI in September 2026",
            category="us_cpi",
            open_time=datetime(2026, 9, 17, 10, tzinfo=kst),
            close_time=utc(2),
            status="open",
            created_at=utc(),
            updated_at=utc(),
        )


def test_market_snapshot_rejects_reversed_quotes() -> None:
    with pytest.raises(ValidationError, match="yes bid exceeds yes ask"):
        MarketSnapshotRecord(
            event_id="KXCPI-26SEP",
            market_ticker="KXCPI-26SEP-T0.3",
            observed_at=utc(),
            yes_bid=Decimal("0.70"),
            yes_ask=Decimal("0.60"),
            no_bid=Decimal("0.40"),
            no_ask=Decimal("0.50"),
            last_price=Decimal("0.65"),
            volume=Decimal("100"),
            open_interest=Decimal("50"),
            raw_payload_hash="a" * 64,
        )


def test_orderbook_level_requires_non_negative_quantity() -> None:
    with pytest.raises(ValidationError):
        OrderBookSnapshotRecord(
            event_id="KXCPI-26SEP",
            market_ticker="KXCPI-26SEP-T0.3",
            observed_at=utc(),
            side="yes",
            price=Decimal("0.42"),
            quantity=Decimal("-1"),
            level=0,
            raw_payload_hash="b" * 64,
        )


def test_asian_session_date_may_be_next_utc_calendar_day() -> None:
    price = AssetPriceRecord(
        source="licensed-fixture",
        symbol="069500",
        venue="XKRX",
        observed_at=datetime(2026, 9, 21, 23, 30, tzinfo=UTC),
        session_date=date(2026, 9, 22),
        currency="KRW",
        close=Decimal("50123.50"),
        raw_payload_hash="c" * 64,
    )

    assert price.session_date == date(2026, 9, 22)

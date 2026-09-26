from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

VENUE_TIMEZONES = {"XNYS": ZoneInfo("America/New_York"), "XKRX": ZoneInfo("Asia/Seoul")}


def trading_session_date(observed_at: datetime, *, venue: str) -> date:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    try:
        venue_timezone = VENUE_TIMEZONES[venue]
    except KeyError as error:
        raise ValueError(f"unsupported venue: {venue}") from error
    return observed_at.astimezone(venue_timezone).date()


def require_trading_day(session: date, *, holidays: Iterable[date] = ()) -> None:
    if session.weekday() >= 5 or session in set(holidays):
        raise ValueError(f"{session.isoformat()} is not a trading day")


def latest_at_or_before[T](
    rows: Iterable[T], *, feature_as_of: datetime, timestamp: Callable[[T], datetime]
) -> T:
    if feature_as_of.tzinfo is None or feature_as_of.utcoffset() is None:
        raise ValueError("feature_as_of must be timezone-aware")
    if feature_as_of.utcoffset() != UTC.utcoffset(feature_as_of):
        raise ValueError("feature_as_of must be stored in UTC")
    eligible = [row for row in rows if timestamp(row) <= feature_as_of]
    if not eligible:
        raise ValueError("no observation exists at or before feature_as_of")
    return max(eligible, key=timestamp)

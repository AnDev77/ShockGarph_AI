from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# Nasdaq's published US equities holiday schedule, checked on 2026-10-19.
# This is a scheduled calendar, not a record of unscheduled market closures.
NASDAQ_2026_SOURCE = "https://www.nasdaq.com/market-activity/stock-market-holiday-schedule"
NASDAQ_2026_VERSION = "nasdaq-us-equities-2026-checked-2026-10-19"
_NEW_YORK = ZoneInfo("America/New_York")
_CLOSED = frozenset(
    date.fromisoformat(day)
    for day in (
        "2026-01-01",
        "2026-01-19",
        "2026-02-16",
        "2026-04-03",
        "2026-05-25",
        "2026-06-19",
        "2026-07-03",
        "2026-09-07",
        "2026-11-26",
        "2026-12-25",
    )
)
_EARLY_CLOSE = frozenset((date(2026, 11, 27), date(2026, 12, 24)))


@dataclass(frozen=True, slots=True)
class ScheduledSession:
    session_date: date
    close_at: datetime


def nasdaq_2026_sessions(start: date, end: date) -> tuple[ScheduledSession, ...]:
    """Return independently scheduled regular-session closes in UTC for 2026."""
    if start.year != 2026 or end.year != 2026 or end < start:
        raise ValueError("the reviewed Nasdaq calendar covers only a valid 2026 date range")
    sessions = []
    day = start
    while day <= end:
        if day.weekday() < 5 and day not in _CLOSED:
            local_close = datetime.combine(
                day, time(13) if day in _EARLY_CLOSE else time(16), tzinfo=_NEW_YORK
            )
            sessions.append(ScheduledSession(day, local_close.astimezone(UTC)))
        day += timedelta(days=1)
    return tuple(sessions)

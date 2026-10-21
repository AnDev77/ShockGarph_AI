from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# Nasdaq's published US equities schedules, checked on 2026-10-21. The 2025
# annual calendar was amended by an exchange alert for the Carter closure.
# This reviewed range is finite: do not extrapolate holidays to other years.
NASDAQ_2026_SOURCE = "https://www.nasdaq.com/market-activity/stock-market-holiday-schedule"
NASDAQ_2026_VERSION = "nasdaq-us-equities-2026-checked-2026-10-19"
NASDAQ_CALENDAR_SOURCE = "https://www.nasdaqtrader.com/trader.aspx?id=calendar"
NASDAQ_CALENDAR_VERSION = "nasdaq-us-equities-2024-2026-checked-2026-10-21"
_NEW_YORK = ZoneInfo("America/New_York")
_CLOSED_BY_YEAR = {
    2024: (
        "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29",
        "2024-05-27", "2024-06-19", "2024-07-04", "2024-09-02",
        "2024-11-28", "2024-12-25",
    ),
    2025: (
        "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17",
        "2025-04-18", "2025-05-26", "2025-06-19", "2025-07-04",
        "2025-09-01", "2025-11-27", "2025-12-25",
    ),
    2026: (
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
    ),
}
_CLOSED = frozenset(date.fromisoformat(day) for year in _CLOSED_BY_YEAR
                    for day in _CLOSED_BY_YEAR[year])
_EARLY_CLOSE = frozenset(date.fromisoformat(day) for day in (
    "2024-07-03", "2024-11-29", "2024-12-24",
    "2025-07-03", "2025-11-28", "2025-12-24",
    "2026-11-27", "2026-12-24",
))


@dataclass(frozen=True, slots=True)
class ScheduledSession:
    session_date: date
    close_at: datetime


def nasdaq_sessions(start: date, end: date) -> tuple[ScheduledSession, ...]:
    """Return reviewed 2024–2026 Nasdaq US equity regular-session closes in UTC."""
    if not 2024 <= start.year <= end.year <= 2026 or end < start:
        raise ValueError("the reviewed Nasdaq calendar covers only 2024 through 2026")
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


def nasdaq_2026_sessions(start: date, end: date) -> tuple[ScheduledSession, ...]:
    """Keep the original 2026-only API for existing callers."""
    if start.year != 2026 or end.year != 2026 or end < start:
        raise ValueError("the reviewed Nasdaq calendar covers only a valid 2026 date range")
    return nasdaq_sessions(start, end)

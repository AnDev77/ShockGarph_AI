"""Completed-session capture policy; no assumption of provider finality."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from shockgraph_data_pipeline.market_calendar import nasdaq_sessions

# Project safety buffer, not a promise that the provider never revises a bar.
DAILY_CAPTURE_LAG = timedelta(hours=1)
SIP_DELAY = timedelta(minutes=15)
_NEW_YORK = ZoneInfo("America/New_York")


def _utc(now: datetime) -> datetime:
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("capture clock must be UTC")
    return now.astimezone(UTC)


def latest_capture_session(now: datetime) -> date:
    """Choose the most recent reviewed close that passed the safety buffer."""
    now = _utc(now)
    end = now.astimezone(_NEW_YORK).date()
    if not 2024 <= end.year <= 2026:
        raise ValueError("capture date is outside the reviewed calendar")
    start = max(date(2024, 1, 1), end - timedelta(days=14))
    completed = [row.session_date for row in nasdaq_sessions(start, end)
                 if row.close_at + DAILY_CAPTURE_LAG <= now]
    if not completed:
        raise ValueError("no completed capture session")
    return completed[-1]


def alpaca_request_end(end: date, now: datetime) -> str:
    """Bound the SIP query at least 15 minutes behind an actual request clock."""
    now = _utc(now)
    if end > latest_capture_session(now):
        raise ValueError("request must end at a completed capture session")
    cutoff = min(datetime.combine(end, time(23, 59, 59), tzinfo=UTC), now - SIP_DELAY)
    return cutoff.isoformat().replace("+00:00", "Z")

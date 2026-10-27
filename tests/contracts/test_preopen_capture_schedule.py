"""Keep the private scheduled capture ahead of the next market opening."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from shockgraph_data_pipeline.market_calendar import nasdaq_sessions


def test_capture_schedule_allows_the_observed_delay_and_preopen_archive() -> None:
    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows"
                / "private-forward-capture.yml").read_text(encoding="utf-8")
    match = re.search(r"cron: '([0-9]+) ([0-9]+) \* \* 1-5'", workflow)
    assert match is not None
    minute, hour = map(int, match.groups())
    assert "timezone: America/New_York" in workflow

    ny = ZoneInfo("America/New_York")
    for session_day in (date(2026, 10, 26), date(2026, 10, 27),
                        date(2026, 11, 3)):
        planned = datetime.combine(session_day, time(hour, minute), ny).astimezone(UTC)
        last_complete = nasdaq_sessions(session_day - timedelta(days=7),
                                        session_day - timedelta(days=1))[-1]
        next_open = datetime.combine(session_day, time(9, 30), ny).astimezone(UTC)
        assert last_complete.close_at < planned
        # The first scheduled run started 6h08m50s late. This headroom still
        # leaves the archive's required one hour before the next opening.
        assert planned + timedelta(hours=6, minutes=9) <= next_open - timedelta(hours=1)

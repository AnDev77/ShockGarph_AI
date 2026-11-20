from datetime import UTC, date, datetime

import pytest
from shockgraph_data_pipeline.capture_window import alpaca_request_end, latest_capture_session


@pytest.mark.parametrize(("now", "origin"), [
    ("2026-11-19T21:59:59Z", "2026-11-18"),
    ("2026-11-19T22:00:00Z", "2026-11-19"),
    ("2026-11-20T01:23:00Z", "2026-11-19"),
    ("2026-11-20T11:23:00Z", "2026-11-19"),
    ("2026-11-23T05:23:00Z", "2026-11-20"),
    ("2026-11-26T22:00:00Z", "2026-11-25"),
    ("2026-11-27T18:59:59Z", "2026-11-25"),
    ("2026-11-27T19:00:00Z", "2026-11-27"),
    ("2026-07-02T21:00:00Z", "2026-07-02"),
])
def test_capture_window_tracks_close_delay_holidays_dst_and_retries(now, origin) -> None:
    assert latest_capture_session(datetime.fromisoformat(now)) == date.fromisoformat(origin)


def test_request_end_respects_delayed_sip_without_requiring_next_calendar_day() -> None:
    assert alpaca_request_end(date(2026, 11, 19), datetime(2026, 11, 19, 22, tzinfo=UTC)) == (
        "2026-11-19T21:45:00Z"
    )
    assert alpaca_request_end(date(2026, 11, 19), datetime(2026, 11, 20, 1, tzinfo=UTC)) == (
        "2026-11-19T23:59:59Z"
    )
    with pytest.raises(ValueError):
        alpaca_request_end(date(2026, 11, 19), datetime(2026, 11, 19, 21, 59, tzinfo=UTC))
    with pytest.raises(ValueError):
        alpaca_request_end(date(2026, 11, 20), datetime(2026, 11, 19, 22, tzinfo=UTC))
    for invalid in [datetime(2026, 11, 19), datetime(2027, 1, 2, tzinfo=UTC)]:
        with pytest.raises(ValueError):
            latest_capture_session(invalid)

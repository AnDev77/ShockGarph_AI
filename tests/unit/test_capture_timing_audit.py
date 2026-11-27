from datetime import UTC, date, datetime

import pytest

from scripts.audit_capture_timing import audit_timing, aware_utc, main


@pytest.mark.parametrize(("origin", "created", "expected_day", "deadline"), [
    ("2026-11-13", "2026-11-16T12:10:00+00:00", "2026-11-16", "2026-11-16T13:30:00+00:00"),
    ("2026-07-02", "2026-07-06T11:10:00+00:00", "2026-07-06", "2026-07-06T12:30:00+00:00"),
])
def test_reviewed_holiday_weekend_and_dst(origin, created, expected_day, deadline) -> None:
    started = aware_utc(created)
    result = audit_timing(origin=date.fromisoformat(origin), created_at=started, started_at=started)
    assert result["status"] == "started_with_preopen_headroom"
    assert result["first_outcome_session"] == expected_day
    assert result["preopen_deadline_at"] == deadline
    assert result["archive_receipt_verified"] is False
    assert result["public_performance_allowed"] is False


@pytest.mark.parametrize(("created", "started", "status"), [
    ("2026-11-18T20:25:14Z", "2026-11-18T20:26:00Z", "created_after_preopen_deadline"),
    ("2026-11-18T12:10:00Z", "2026-11-18T13:30:01Z", "started_after_preopen_deadline"),
    ("2026-11-18T13:30:00Z", "2026-11-18T13:30:00Z", "started_with_preopen_headroom"),
])
def test_public_run_timing_is_not_archive_receipt(created, started, status) -> None:
    result = audit_timing(origin=date(2026, 11, 17), created_at=aware_utc(created),
                          started_at=aware_utc(started))
    assert result["status"] == status
    assert result["archive_receipt_verified"] is False


def test_reject_invalid_chronology_and_non_session() -> None:
    now = datetime(2026, 11, 18, 12, tzinfo=UTC)
    with pytest.raises(ValueError, match="timezone"):
        aware_utc("2026-11-18T12:00:00")
    with pytest.raises(ValueError, match="timezone"):
        audit_timing(origin=date(2026, 11, 17), created_at=now.replace(tzinfo=None),
                     started_at=now)
    with pytest.raises(ValueError, match="precedes"):
        audit_timing(origin=date(2026, 11, 17), created_at=now,
                     started_at=datetime(2026, 11, 18, 11, tzinfo=UTC))
    with pytest.raises(ValueError, match="trading session"):
        audit_timing(origin=date(2026, 11, 15), created_at=now, started_at=now)
    with pytest.raises(ValueError, match="not closed"):
        audit_timing(origin=date(2026, 11, 18), created_at=now, started_at=now)
    year_end = datetime(2026, 12, 31, 23, tzinfo=UTC)
    assert audit_timing(origin=date(2026, 12, 24), created_at=year_end,
                        started_at=year_end)["status"] == "reviewed_calendar_exhausted"
    assert audit_timing(origin=date(2026, 12, 31), created_at=year_end,
                        started_at=year_end)["status"] == "reviewed_calendar_exhausted"


def test_cli_outputs_allowlisted_metadata_and_generic_failure(capsys) -> None:
    assert main(["--origin-session", "2026-11-15", "--created-at", "2026-11-18T12:00Z",
                 "--started-at", "2026-11-18T12:00Z"]) == 2
    assert capsys.readouterr().out.strip() == '{"status": "capture_timing_audit_failed"}'

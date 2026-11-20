"""Explain preopen feasibility from a declared price origin and public run metadata."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/data_pipeline"))

from shockgraph_data_pipeline.market_calendar import nasdaq_sessions  # noqa: E402


def aware_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp requires an explicit timezone")
    return parsed.astimezone(UTC)


def audit_timing(*, origin: date, created_at: datetime, started_at: datetime) -> dict[str, object]:
    """This is feasibility, never evidence that a forecast was actually stored."""
    if any(value.tzinfo is None or value.utcoffset() is None
           for value in (created_at, started_at)):
        raise ValueError("timestamps require an explicit timezone")
    if started_at < created_at:
        raise ValueError("run start precedes creation")
    origin_sessions = nasdaq_sessions(origin, origin)
    if not origin_sessions:
        raise ValueError("price origin is not a reviewed trading session")
    if origin_sessions[0].close_at > created_at:
        raise ValueError("price origin has not closed at run creation")
    if origin == date(2026, 12, 31):
        return {"status": "reviewed_calendar_exhausted", "public_performance_allowed": False}
    sessions = nasdaq_sessions(origin + timedelta(days=1), date(2026, 12, 31))
    if len(sessions) < 20:
        return {"status": "reviewed_calendar_exhausted", "public_performance_allowed": False}
    next_day = sessions[0].session_date
    opening = datetime.combine(next_day, time(9, 30), tzinfo=ZoneInfo("America/New_York"))
    deadline = opening.astimezone(UTC) - timedelta(hours=1)
    status = ("created_after_preopen_deadline" if created_at > deadline else
              "started_after_preopen_deadline" if started_at > deadline else
              "started_with_preopen_headroom")
    return {
        "status": status,
        "origin_session": origin.isoformat(),
        "first_outcome_session": next_day.isoformat(),
        "preopen_deadline_at": deadline.isoformat(),
        "run_created_at": created_at.astimezone(UTC).isoformat(),
        "run_started_at": started_at.astimezone(UTC).isoformat(),
        "remaining_seconds_at_start": int((deadline - started_at).total_seconds()),
        "archive_receipt_verified": False,
        "public_performance_allowed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="공개 실행 시각의 사전 예측 가능 여부 감사")
    parser.add_argument("--origin-session", required=True, type=date.fromisoformat)
    parser.add_argument("--created-at", required=True, type=aware_utc)
    parser.add_argument("--started-at", required=True, type=aware_utc)
    args = parser.parse_args(argv)
    try:
        report = audit_timing(
            origin=args.origin_session, created_at=args.created_at, started_at=args.started_at,
        )
    except ValueError:
        print(json.dumps({"status": "capture_timing_audit_failed"}))
        return 2
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

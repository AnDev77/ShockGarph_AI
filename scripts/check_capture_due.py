"""Skip a private capture when the same completed US session is archived."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path[:0] = [str(Path(__file__).resolve().parents[1]),
                str(Path(__file__).resolve().parents[1] / "packages/data_pipeline")]

from shockgraph_data_pipeline.capture_window import latest_capture_session  # noqa: E402
from shockgraph_data_pipeline.market_calendar import (  # noqa: E402
    REVIEWED_CALENDAR_END,
    REVIEWED_CALENDAR_START,
    nasdaq_sessions,
    reviewed_future_sessions,
)

from scripts.audit_private_capture import latest_capture  # noqa: E402
from scripts.private_r2 import configured_r2  # noqa: E402


def expected_origin(end: date) -> date:
    """Resolve weekends/holidays using the same calendar as the collector."""
    sessions = nasdaq_sessions(end - timedelta(days=14), end)
    if not sessions:
        raise ValueError("no reviewed price session")
    return sessions[-1].session_date


def capture_due(client: Any, *, bucket: str, prefix: str, end: date) -> bool:
    origin = expected_origin(end)
    try:
        latest = latest_capture(client, bucket=bucket, prefix=prefix)
    except ValueError as error:
        if str(error) != "no archive index exists":
            raise
        return True
    return latest["origin_session"] != origin.isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="동일 거래일 비공개 가격 보관 중복 방지")
    parser.add_argument("--end", type=date.fromisoformat,
                        help="생략하면 실제 시각에 폐장 후 한 시간이 지난 마지막 거래일")
    parser.add_argument("--prefix", default="shockgraph-research")
    args = parser.parse_args(argv)
    try:
        client, bucket = configured_r2()
        end = args.end or latest_capture_session(datetime.now(UTC))
        due = capture_due(client, bucket=bucket, prefix=args.prefix, end=end)
        origin = expected_origin(end)
        future = reviewed_future_sessions(origin)
        reviewed = nasdaq_sessions(REVIEWED_CALENDAR_START, REVIEWED_CALENDAR_END)
        last_origin = reviewed[-21].session_date
    except Exception:
        print(json.dumps({"status": "capture_preflight_failed"}))
        return 2
    print(json.dumps({"status": "capture_due" if due else "capture_already_archived",
                      "due": due, "origin_session": origin.isoformat(),
                      "price_end": origin.isoformat(),
                      "forecast_calendar_ready": len(future) >= 20,
                      "last_supported_forecast_origin": last_origin.isoformat(),
                      "calendar_end": REVIEWED_CALENDAR_END.isoformat(),
                      "public_performance_allowed": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

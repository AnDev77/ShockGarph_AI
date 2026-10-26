"""Skip a private capture when the same completed US session is archived."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path[:0] = [str(Path(__file__).resolve().parents[1]),
                str(Path(__file__).resolve().parents[1] / "packages/data_pipeline")]

from shockgraph_data_pipeline.market_calendar import nasdaq_sessions  # noqa: E402

from scripts.audit_private_capture import latest_capture  # noqa: E402
from scripts.private_r2 import configured_r2  # noqa: E402


def capture_due(client: Any, *, bucket: str, prefix: str, end: date) -> bool:
    sessions = nasdaq_sessions(end - timedelta(days=14), end)
    if not sessions:
        raise ValueError("no reviewed price session")
    try:
        latest = latest_capture(client, bucket=bucket, prefix=prefix)
    except ValueError as error:
        if str(error) != "no archive index exists":
            raise
        return True
    return latest["origin_session"] != sessions[-1].session_date.isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="동일 거래일 비공개 가격 보관 중복 방지")
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--prefix", default="shockgraph-research")
    args = parser.parse_args(argv)
    try:
        client, bucket = configured_r2()
        due = capture_due(client, bucket=bucket, prefix=args.prefix, end=args.end)
    except Exception:
        print(json.dumps({"status": "capture_preflight_failed"}))
        return 2
    print(json.dumps({"status": "capture_due" if due else "capture_already_archived",
                      "due": due}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

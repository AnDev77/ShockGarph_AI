"""Capture a real Treasury 10-year rate XML snapshot in a local immutable store."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "apps/collector"), str(ROOT / "packages/data_pipeline")]

import httpx  # noqa: E402
from shockgraph_collector.treasury_rates import TreasuryYieldCollector  # noqa: E402
from shockgraph_data_pipeline.raw_store import ImmutableRawStore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="미 재무부 10년물 금리 원본 월별 수집")
    month_now = datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m")
    parser.add_argument("--month", default=month_now, help="수집할 미국 날짜의 월, YYYYMM")
    parser.add_argument("--raw-root", type=Path, default=ROOT / "data/raw")
    args = parser.parse_args(argv)
    try:
        if len(args.month) != 6 or not args.month.isascii() or not args.month.isdecimal():
            raise ValueError("month must use YYYYMM")
        year, month = int(args.month[:4]), int(args.month[4:])
        with TreasuryYieldCollector() as collector:
            capture = collector.collect_month(year, month, ImmutableRawStore(args.raw_root))
        print(json.dumps({
            "status": "archived_research_only", "series": "UST10Y_PAR",
            "month": args.month, "observation_count": len(capture.observations),
            "first_observation_date": capture.observations[0].observation_date.isoformat(),
            "last_observation_date": capture.observations[-1].observation_date.isoformat(),
            "captured_at": capture.captured_at.isoformat(),
            "raw_file_sha256": capture.raw_file_sha256,
            "raw_payload_hash": capture.raw_artifact.payload_sha256,
            "raw_created": capture.raw_artifact.created,
            "provider_release_at_verified": False,
            "point_in_time_model_input_ready": False,
        }, ensure_ascii=False))
    except (OSError, ValueError, ImportError, httpx.HTTPError) as error:
        print(json.dumps({"status": "collection_failed", "reason": str(error)
                          if isinstance(error, ValueError) else "feed could not be collected"},
                         ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

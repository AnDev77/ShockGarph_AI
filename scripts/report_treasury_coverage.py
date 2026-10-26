"""Report price-date overlap with archived Treasury versions without scoring forecasts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "apps/collector"), str(ROOT / "packages/domain"),
                str(ROOT / "packages/data_pipeline"), str(ROOT / "packages/risk_engine")]

from shockgraph_collector.treasury_rates import load_treasury_history  # noqa: E402

from scripts.evaluate_exploratory_history import load_history_prices  # noqa: E402

_EASTERN = ZoneInfo("America/New_York")


def report_coverage(price_path: Path, raw_root: Path) -> dict[str, Any]:
    prices, price_hash = load_history_prices(price_path)
    history = load_treasury_history(raw_root)
    price_dates = {row.session_date for row in prices}
    observation_dates = {row.observation_date for row in history}
    capture_dates = {row.captured_at.astimezone(_EASTERN).date() for row in history}
    first_capture_date = min(capture_dates)
    # Without a prediction timestamp, a capture on the same US session is not established
    # as available by the time its closing price was used. Count only later sessions.
    strictly_later_price_dates = [day for day in price_dates if day > first_capture_date]
    potentially_known_dates = {
        day for day in strictly_later_price_dates
        if any(row.captured_at.astimezone(_EASTERN).date() < day
               and row.observation_date <= day for row in history)
    }
    archive_digest = hashlib.sha256("\n".join(
        f"{row.observation_date}:{row.captured_at.isoformat()}:{row.raw_file_sha256}"
        for row in history
    ).encode("utf-8")).hexdigest()
    return {
        "status": "descriptive_coverage_only", "symbol": "TLT", "series": "UST10Y_PAR",
        "price_file_sha256": price_hash, "treasury_archive_sha256": archive_digest,
        "price_session_count": len(price_dates),
        "treasury_vintage_count": len(history),
        "treasury_unique_observation_dates": len(observation_dates),
        "same_date_observation_overlap": len(price_dates & observation_dates),
        "first_capture_us_date": first_capture_date.isoformat(),
        "price_sessions_strictly_after_first_capture": len(strictly_later_price_dates),
        "sessions_with_earlier_treasury_capture": len(potentially_known_dates),
        "price_vintages_verified": False,
        "exact_prediction_times_verified": False,
        "public_performance_allowed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TLT 가격과 보관 재무부 금리의 날짜 겹침")
    parser.add_argument("--price-history", type=Path, required=True)
    parser.add_argument("--treasury-archive", type=Path, default=ROOT / "data/raw")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(report_coverage(args.price_history, args.treasury_archive),
                         ensure_ascii=False, indent=2))
    except ValueError as error:
        print(json.dumps(
            {"status": "invalid_input", "reason": str(error)},
            ensure_ascii=False,
        ))
        return 2
    except OSError:
        print(json.dumps(
            {"status": "invalid_input", "reason": "input file could not be read"},
            ensure_ascii=False,
        ))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

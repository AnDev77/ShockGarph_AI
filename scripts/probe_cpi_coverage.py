from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "apps/collector"), str(ROOT / "packages/data_pipeline")]

from shockgraph_collector.client import KalshiPublicClient, RetryPolicy  # noqa: E402


def inventory(client: KalshiPublicClient, path: str, *, max_pages: int) -> dict[str, Any]:
    events, contracts, seen_cursors = set(), set(), set()
    cursor = ""
    complete = False
    for _ in range(max_pages):
        params: dict[str, Any] = {"series_ticker": "KXCPI", "limit": 100}
        if cursor:
            params["cursor"] = cursor
        payload = client.get_json(path, params=params)
        markets = payload.get("markets")
        if not isinstance(markets, list):
            raise ValueError("markets must be a list")
        for market in markets:
            if not isinstance(market, dict):
                raise ValueError("invalid market")
            ticker, event = market.get("ticker"), market.get("event_ticker")
            if not isinstance(ticker, str) or not isinstance(event, str):
                raise ValueError("missing contract identity")
            if not event.startswith("KXCPI-"):
                raise ValueError("series filter mismatch")
            contracts.add(ticker)
            if market.get("result") in ("yes", "no"):
                events.add(event)
        cursor = payload.get("cursor", "")
        if not isinstance(cursor, str):
            raise ValueError("invalid cursor")
        if not cursor:
            complete = True
            break
        if cursor in seen_cursors:
            raise ValueError("repeated cursor")
        seen_cursors.add(cursor)
    # Only aggregate coverage is returned. No response bodies or probability values are persisted.
    return {
        "status": "ok" if complete else "partial",
        "complete": complete,
        "observed_contracts": len(contracts),
        "observed_resolved_events": len(events),
        "pre_release_candle_coverage": "not_verified",
    }


def probe(*, max_pages: int = 10) -> dict[str, Any]:
    if max_pages < 1:
        raise ValueError("max_pages must be positive")
    report: dict[str, Any] = {
        "checked_at": datetime.now(UTC).isoformat(),
        "series": "KXCPI",
        "raw_responses_saved": False,
        "endpoints": {},
        "assets": {a: "not_verified" for a in ("SPY", "TLT", "GLD")},
        "credentials": {
            name: bool(os.environ.get(name)) for name in ("FRED_API_KEY", "ALPHA_VANTAGE_API_KEY")
        },
        "joint_dataset_status": "not_verified",
    }
    try:
        with KalshiPublicClient(timeout_seconds=8, retry_policy=RetryPolicy(max_attempts=1)) as c:
            for path in ("/historical/cutoff", "/markets", "/historical/markets"):
                try:
                    if path.endswith("cutoff"):
                        payload = c.get_json(path)
                        if not isinstance(payload.get("market_settled_ts"), str):
                            raise ValueError("cutoff schema mismatch")
                        result = {"status": "ok"}
                    else:
                        result = inventory(c, path, max_pages=max_pages)
                    report["endpoints"][path] = result
                except (httpx.HTTPError, ValueError) as error:
                    report["endpoints"][path] = {
                        "status": "error",
                        "error_type": type(error).__name__,
                        "http_status": error.response.status_code
                        if isinstance(error, httpx.HTTPStatusError)
                        else None,
                    }
    except ImportError:
        report["environment_error"] = (
            "proxy dependency unavailable; install httpx[socks] if required"
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="CPI 공개 API의 제한된 읽기 전용 커버리지 점검")
    parser.add_argument("--max-pages", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(probe(max_pages=args.max_pages), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

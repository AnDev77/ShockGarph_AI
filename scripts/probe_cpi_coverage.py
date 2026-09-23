from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "apps/collector"), str(ROOT / "packages/data_pipeline")]

from shockgraph_collector.client import KalshiPublicClient, RetryPolicy  # noqa: E402

DEFAULT_EVENT = "KXCPI-26AUG"
# BLS August 2026 CPI release: September 11, 2026 08:30 ET (12:30 UTC).
DEFAULT_RELEASE_AT = datetime(2026, 9, 11, 12, 30, tzinfo=UTC)


def _valid_decimal(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def inspect_pre_release_candles(payload: dict[str, Any], prediction_at: datetime) -> dict[str, Any]:
    candles = payload.get("candlesticks")
    if not isinstance(candles, list):
        raise ValueError("candlesticks must be a list")
    valid_ends: set[int] = set()
    earliest = int((prediction_at - timedelta(hours=1)).timestamp())
    latest = int(prediction_at.timestamp())
    for candle in candles:
        if not isinstance(candle, dict):
            continue
        end = candle.get("end_period_ts")
        if isinstance(end, bool) or not isinstance(end, int) or not earliest <= end <= latest:
            continue
        bid = candle.get("yes_bid")
        ask = candle.get("yes_ask")
        if not isinstance(bid, dict) or not isinstance(ask, dict):
            continue
        buy = _valid_decimal(bid.get("close_dollars", bid.get("close")))
        sell = _valid_decimal(ask.get("close_dollars", ask.get("close")))
        volume = _valid_decimal(candle.get("volume_fp", candle.get("volume")))
        if (
            buy is not None
            and sell is not None
            and volume is not None
            and Decimal(0) <= buy <= sell <= Decimal(1)
            and sell - buy <= Decimal("0.10")
            and volume > 0
        ):
            valid_ends.add(end)
    return {
        "candidate_candles": len(candles),
        "eligible_candles": len(valid_ends),
        "near_release_candles": sum(end >= latest - 15 * 60 for end in valid_ends),
        "latest_eligible_end_at": datetime.fromtimestamp(max(valid_ends), UTC).isoformat()
        if valid_ends
        else None,
        "screen": "pre_release_end,positive_volume,valid_bid_ask,spread_at_most_0.10",
    }


def sample_pre_release(
    client: KalshiPublicClient, *, event_ticker: str, release_at: datetime
) -> dict[str, Any]:
    if not re.fullmatch(r"KXCPI-[A-Z0-9-]+", event_ticker):
        raise ValueError("require a CPI event ticker")
    if release_at.tzinfo is None or release_at.utcoffset() != timedelta(0):
        raise ValueError("release_at must be timezone-aware UTC")
    prediction_at = release_at - timedelta(minutes=5)
    candidates: list[tuple[str, dict[str, Any]]] = []
    errors: dict[str, dict[str, Any]] = {}
    for path in ("/historical/markets", "/markets"):
        try:
            payload = client.get_json(path, params={"event_ticker": event_ticker, "limit": 100})
            markets = payload.get("markets")
            if not isinstance(markets, list):
                raise ValueError("markets must be a list")
            for market in markets:
                if (
                    isinstance(market, dict)
                    and market.get("event_ticker") == event_ticker
                    and market.get("result") in ("yes", "no")
                    and isinstance(market.get("ticker"), str)
                    and market["ticker"].startswith(event_ticker + "-")
                    and re.fullmatch(r"[A-Z0-9.\-]+", market["ticker"])
                ):
                    candidates.append((path, market))
        except (httpx.HTTPError, ValueError) as error:
            errors[path] = {
                "error_type": type(error).__name__,
                "http_status": error.response.status_code
                if isinstance(error, httpx.HTTPStatusError)
                else None,
            }
    if not candidates:
        return {
            "status": "access_error" if errors else "no_resolved_market",
            "market_access_errors": errors,
        }
    # Only a coverage probe: fixed ordering avoids selecting a contract by ex-post volume/outcome.
    path, market = min(candidates, key=lambda pair: (pair[1]["ticker"], pair[0]))
    ticker = market["ticker"]
    candle_path = f"{path}/{ticker}/candlesticks"
    try:
        payload = client.get_json(
            candle_path,
            params={
                "start_ts": int((prediction_at - timedelta(hours=1)).timestamp()),
                "end_ts": int(prediction_at.timestamp()),
                "period_interval": 1,
            },
        )
        screen = inspect_pre_release_candles(payload, prediction_at)
    except (httpx.HTTPError, ValueError) as error:
        return {
            "status": "candle_access_error",
            "ticker": ticker,
            "market_access_errors": errors,
            "error_type": type(error).__name__,
            "http_status": error.response.status_code
            if isinstance(error, httpx.HTTPStatusError)
            else None,
        }
    return {
        "status": "eligible"
        if screen["near_release_candles"]
        else ("stale_candles" if screen["eligible_candles"] else "no_eligible_candles"),
        "ticker": ticker,
        "event_ticker": event_ticker,
        "prediction_at": prediction_at.isoformat(),
        "market_access_errors": errors,
        **screen,
    }


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


def probe(
    *,
    max_pages: int = 10,
    event_ticker: str = DEFAULT_EVENT,
    release_at: datetime = DEFAULT_RELEASE_AT,
) -> dict[str, Any]:
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
            for path in ("/exchange/status", "/series/KXCPI"):
                try:
                    response = c.get_json(path)
                    report["endpoints"][path] = {"status": "ok" if response else "empty_response"}
                except (httpx.HTTPError, ValueError) as error:
                    report["endpoints"][path] = {
                        "status": "error",
                        "error_type": type(error).__name__,
                        "http_status": error.response.status_code
                        if isinstance(error, httpx.HTTPStatusError)
                        else None,
                    }
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
            report["historical_pre_release_sample"] = sample_pre_release(
                c, event_ticker=event_ticker, release_at=release_at
            )
    except ImportError:
        report["environment_error"] = (
            "proxy dependency unavailable; install httpx[socks] if required"
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="CPI 공개 API의 제한된 읽기 전용 커버리지 점검")
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--event-ticker", default=DEFAULT_EVENT)
    parser.add_argument("--release-at", default=DEFAULT_RELEASE_AT.isoformat())
    args = parser.parse_args()
    print(
        json.dumps(
            probe(
                max_pages=args.max_pages,
                event_ticker=args.event_ticker,
                release_at=datetime.fromisoformat(args.release_at.replace("Z", "+00:00")),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

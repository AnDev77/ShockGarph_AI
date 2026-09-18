from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
DEMO_BASE_URL = "https://external-api.demo.kalshi.co/trade-api/v2"
TARGET_SERIES = {
    "fomc": "KXFEDDECISION",
    "us_cpi": "KXCPI",
    "oil": "KXOIL",
}
USER_AGENT = "shockgraph-ai-feasibility-probe/0.1"


def fetch_json(
    path: str,
    params: Mapping[str, Any] | None = None,
    *,
    base_url: str = BASE_URL,
) -> dict[str, Any]:
    query = f"?{urlencode(params)}" if params else ""
    request = Request(f"{base_url}{path}{query}", headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=45) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise TypeError(f"Expected an object from {path}")
    return payload


def iter_pages(
    path: str,
    collection_key: str,
    params: Mapping[str, Any],
) -> Iterator[dict[str, Any]]:
    cursor = ""
    while True:
        page_params = dict(params)
        if cursor:
            page_params["cursor"] = cursor
        payload = fetch_json(path, page_params)
        items = payload.get(collection_key, [])
        if not isinstance(items, list):
            raise TypeError(f"{collection_key} must be a list")
        for item in items:
            if isinstance(item, dict):
                yield item
        cursor = payload.get("cursor", "")
        if not cursor:
            break


def iso_range(markets: list[dict[str, Any]]) -> dict[str, str | None]:
    timestamps = sorted(
        value
        for market in markets
        if isinstance((value := market.get("settlement_ts")), str) and value
    )
    return {
        "first_settlement": timestamps[0] if timestamps else None,
        "last_settlement": timestamps[-1] if timestamps else None,
    }


def series_coverage(series_ticker: str) -> dict[str, Any]:
    events = list(
        iter_pages(
            "/events",
            "events",
            {"limit": 200, "series_ticker": series_ticker},
        )
    )
    recent_markets = list(
        iter_pages(
            "/markets",
            "markets",
            {"limit": 1000, "series_ticker": series_ticker, "mve_filter": "exclude"},
        )
    )
    historical_markets = list(
        iter_pages(
            "/historical/markets",
            "markets",
            {"limit": 1000, "series_ticker": series_ticker},
        )
    )

    markets_by_ticker = {
        market["ticker"]: market
        for market in [*historical_markets, *recent_markets]
        if isinstance(market.get("ticker"), str)
    }
    markets = list(markets_by_ticker.values())
    resolved_markets = [market for market in markets if market.get("result") in {"yes", "no"}]
    resolved_events = {
        market["event_ticker"]
        for market in resolved_markets
        if isinstance(market.get("event_ticker"), str)
    }

    return {
        "series_ticker": series_ticker,
        "event_count": len({event.get("event_ticker") for event in events}),
        "market_count": len(markets),
        "resolved_market_count": len(resolved_markets),
        "resolved_event_count": len(resolved_events),
        "recent_market_count": len(recent_markets),
        "historical_market_count": len(historical_markets),
        **iso_range(resolved_markets),
        "sample_historical_ticker": historical_markets[0].get("ticker")
        if historical_markets
        else None,
    }


def probe_endpoint(path: str, key: str, params: Mapping[str, Any]) -> dict[str, Any]:
    try:
        payload = fetch_json(path, params)
        items = payload.get(key)
        return {
            "status": "ok",
            "sample_count": len(items) if isinstance(items, list) else None,
            "response_keys": sorted(payload),
            "has_cursor": bool(payload.get("cursor")),
        }
    except (HTTPError, URLError, TimeoutError, ValueError, TypeError) as error:
        return {"status": "error", "error": str(error)}


def probe_candles(market: Mapping[str, Any]) -> dict[str, Any]:
    ticker = market.get("sample_historical_ticker")
    if not isinstance(ticker, str):
        return {"status": "unavailable", "reason": "no historical market sample"}
    try:
        detail = fetch_json(f"/historical/markets/{ticker}").get("market", {})
        start = datetime.fromisoformat(detail["open_time"].replace("Z", "+00:00"))
        end_value = detail.get("settlement_ts") or detail.get("close_time")
        end = datetime.fromisoformat(end_value.replace("Z", "+00:00"))
        payload = fetch_json(
            f"/historical/markets/{ticker}/candlesticks",
            {
                "start_ts": int(start.timestamp()),
                "end_ts": int(end.timestamp()),
                "period_interval": 1440,
            },
        )
        candles = payload.get("candlesticks", [])
        return {"status": "ok", "ticker": ticker, "daily_candle_count": len(candles)}
    except (HTTPError, URLError, TimeoutError, KeyError, ValueError, TypeError) as error:
        return {"status": "error", "ticker": ticker, "error": str(error)}


def probe_orderbook() -> dict[str, Any]:
    try:
        markets = fetch_json(
            "/markets", {"limit": 1, "status": "open", "mve_filter": "exclude"}
        ).get("markets", [])
        if not markets:
            return {"status": "unavailable", "reason": "no open market sample"}
        ticker = markets[0]["ticker"]
        payload = fetch_json(f"/markets/{ticker}/orderbook", {"depth": 5})
        return {"status": "ok", "ticker": ticker, "response_keys": sorted(payload)}
    except HTTPError as error:
        return {"status": "http_error", "http_status": error.code}
    except (URLError, TimeoutError, KeyError, ValueError, TypeError) as error:
        return {"status": "error", "error": str(error)}


def main() -> int:
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": BASE_URL,
        "endpoints": {
            "events": probe_endpoint("/events", "events", {"limit": 3}),
            "markets": probe_endpoint("/markets", "markets", {"limit": 3}),
            "trades": probe_endpoint("/markets/trades", "trades", {"limit": 3}),
            "historical_markets": probe_endpoint(
                "/historical/markets", "markets", {"limit": 3}
            ),
            "historical_trades": probe_endpoint(
                "/historical/trades", "trades", {"limit": 3}
            ),
        },
    }

    try:
        report["historical_cutoff"] = fetch_json("/historical/cutoff")
        report["series"] = {
            name: series_coverage(ticker) for name, ticker in TARGET_SERIES.items()
        }
        report["historical_candlesticks"] = probe_candles(report["series"]["us_cpi"])
        report["orderbook"] = probe_orderbook()
        report["demo_markets"] = probe_endpoint(
            "/markets",
            "markets",
            {"limit": 1},
        )
        try:
            demo_payload = fetch_json("/markets", {"limit": 1}, base_url=DEMO_BASE_URL)
            report["demo_markets"] = {
                "status": "ok",
                "sample_count": len(demo_payload.get("markets", [])),
                "response_keys": sorted(demo_payload),
            }
        except (HTTPError, URLError, TimeoutError, ValueError, TypeError) as error:
            report["demo_markets"] = {"status": "error", "error": str(error)}
    except (HTTPError, URLError, TimeoutError, ValueError, TypeError) as error:
        report["fatal_error"] = str(error)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

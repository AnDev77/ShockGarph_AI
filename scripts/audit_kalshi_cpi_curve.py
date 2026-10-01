from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "apps/collector"),
    str(ROOT / "packages/data_pipeline"),
    str(ROOT / "packages/event_study"),
    str(ROOT / "scripts"),
]

from probe_cpi_coverage import inspect_pre_release_candles  # noqa: E402
from shockgraph_analytics.cpi_distribution import (  # noqa: E402
    ThresholdQuote,
    build_threshold_distribution,
)
from shockgraph_collector.client import (  # noqa: E402
    PRODUCTION_COMPAT_BASE_URL,
    KalshiPublicClient,
    RetryPolicy,
)
from shockgraph_data_pipeline.raw_store import ImmutableRawStore  # noqa: E402

SCHEMA_VERSION = "kalshi-cpi-threshold-curve-v1"
EVENT_PATTERN = re.compile(r"KXCPI-[A-Z0-9-]+")


def _decimal(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def parse_threshold_market(
    market: dict[str, Any], event_ticker: str
) -> tuple[float | None, str | None]:
    """방향성 KXCPI 시장인지 보수적으로 확인하고 임계값을 반환한다."""
    if market.get("event_ticker") != event_ticker:
        return None, "event_mismatch"
    ticker = market.get("ticker")
    if not isinstance(ticker, str):
        return None, "missing_ticker"
    match = re.fullmatch(rf"{re.escape(event_ticker)}-T(-?(?:\d+(?:\.\d+)?|\.\d+))", ticker)
    if match is None:
        return None, "not_directional_threshold_ticker"
    threshold = _decimal(match.group(1))
    if threshold is None:
        return None, "invalid_ticker_threshold"

    floor = market.get("floor_strike")
    if floor is not None:
        floor_value = _decimal(floor)
        if floor_value is None or floor_value != threshold:
            return None, "floor_strike_mismatch"
    relation = market.get("functional_strike")
    if relation is not None and str(relation).lower() not in {"greater", "greater_than", "gt"}:
        return None, "unsupported_relation"
    return float(threshold), None


def _market_inventory(
    client: KalshiPublicClient,
    store: ImmutableRawStore,
    *,
    event_ticker: str,
) -> list[tuple[str, dict[str, Any]]]:
    inventory: dict[str, tuple[str, dict[str, Any]]] = {}
    for tier, path in (("historical", "/historical/markets"), ("recent", "/markets")):
        params = {"event_ticker": event_ticker, "limit": 1000}
        payload = client.get_json(path, params=params)
        store.save(
            payload,
            source="kalshi",
            endpoint=path,
            request_params=params,
            observed_at=client.clock(),
        )
        markets = payload.get("markets")
        if not isinstance(markets, list) or not all(isinstance(row, dict) for row in markets):
            raise ValueError("markets must be an object list")
        for market in markets:
            ticker = market.get("ticker")
            if isinstance(ticker, str):
                inventory[ticker] = (tier, market)
    return list(inventory.values())


def audit_event_curve(
    client: KalshiPublicClient,
    store: ImmutableRawStore,
    *,
    event_ticker: str,
    as_of: datetime,
    request_interval_seconds: float = 0.2,
    max_isotonic_adjustment: float = 0.05,
) -> dict[str, Any]:
    if EVENT_PATTERN.fullmatch(event_ticker) is None:
        raise ValueError("event_ticker must be a KXCPI event")
    if as_of.tzinfo is None or as_of.utcoffset() != timedelta(0):
        raise ValueError("as_of must be timezone-aware UTC")
    if request_interval_seconds < 0:
        raise ValueError("request_interval_seconds must be nonnegative")

    inventory = _market_inventory(client, store, event_ticker=event_ticker)
    rejections: Counter[str] = Counter()
    candidates: list[tuple[str, dict[str, Any], float]] = []
    for tier, market in inventory:
        threshold, reason = parse_threshold_market(market, event_ticker)
        if reason is not None:
            rejections[reason] += 1
            continue
        assert threshold is not None
        candidates.append((tier, market, threshold))
    candidates.sort(key=lambda row: (row[2], str(row[1].get("ticker", ""))))

    quotes: list[ThresholdQuote] = []
    quote_rows: list[dict[str, Any]] = []
    for tier, market, threshold in candidates:
        ticker = str(market["ticker"])
        path = (
            f"/historical/markets/{ticker}/candlesticks"
            if tier == "historical"
            else f"/series/KXCPI/markets/{ticker}/candlesticks"
        )
        params = {
            "start_ts": int((as_of - timedelta(hours=1)).timestamp()),
            "end_ts": int(as_of.timestamp()),
            "period_interval": 1,
        }
        try:
            payload = client.get_json(path, params=params)
            artifact = store.save(
                payload,
                source="kalshi",
                endpoint=path,
                request_params=params,
                observed_at=client.clock(),
            )
            screen = inspect_pre_release_candles(payload, as_of)
            status = (
                "eligible"
                if screen["near_release_candles"]
                else ("stale" if screen["eligible_candles"] else "no_eligible_candles")
            )
            latest = screen["latest_quote"]
            row: dict[str, Any] = {
                "market_ticker": ticker,
                "threshold": threshold,
                "tier": tier,
                "status": status,
                "event_exclusion_reason": screen["event_exclusion_reason"],
                "candidate_candles": screen["candidate_candles"],
                "eligible_candles": screen["eligible_candles"],
                "near_release_candles": screen["near_release_candles"],
            }
            if status == "eligible" and latest is not None:
                observed_at = datetime.fromisoformat(latest["end_at"])
                quote = ThresholdQuote(
                    event_id=event_ticker,
                    market_ticker=ticker,
                    threshold=threshold,
                    observed_at=observed_at,
                    available_at=observed_at,
                    probability_above=latest["yes_midpoint"],
                    spread=latest["spread"],
                    raw_hash=artifact.payload_sha256,
                )
                quotes.append(quote)
                row.update(
                    probability_above=quote.probability_above,
                    quote_end_at=quote.observed_at.isoformat(),
                    spread=quote.spread,
                    volume=latest["volume"],
                    raw_hash=quote.raw_hash,
                )
            quote_rows.append(row)
        except (httpx.HTTPError, ValueError) as error:
            quote_rows.append(
                {
                    "market_ticker": ticker,
                    "threshold": threshold,
                    "tier": tier,
                    "status": "access_error",
                    "error_type": type(error).__name__,
                    "http_status": error.response.status_code
                    if isinstance(error, httpx.HTTPStatusError)
                    else None,
                }
            )
        time.sleep(request_interval_seconds)

    distribution = None
    curve_error = None
    if len(quotes) >= 2:
        try:
            distribution = build_threshold_distribution(
                quotes,
                as_of=as_of,
                max_isotonic_adjustment=max_isotonic_adjustment,
            ).model_dump(mode="json")
        except ValueError as error:
            curve_error = str(error)
    else:
        curve_error = "at least two eligible threshold quotes required"
    status = "eligible" if distribution is not None else "abstained"
    quote_counts = Counter(str(row["status"]) for row in quote_rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "checked_at": datetime.now(UTC).isoformat(),
        "event_ticker": event_ticker,
        "as_of": as_of.isoformat(),
        "status": status,
        "inventory_markets": len(inventory),
        "candidate_threshold_markets": len(candidates),
        "market_rejection_counts": dict(sorted(rejections.items())),
        "quote_status_counts": dict(sorted(quote_counts.items())),
        "contract_definition": "single_decimal_cpi_mom_strictly_greater_percentage_point",
        "max_isotonic_adjustment": max_isotonic_adjustment,
        "curve_error": curve_error,
        "distribution": distribution,
        "consensus_status": "not_provided",
        "quotes": quote_rows,
    }


def save_report(report: dict[str, Any], output_dir: Path) -> Path:
    content = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    run_id = hashlib.sha256(content.encode()).hexdigest()
    directory = output_dir / run_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "report.json"
    if path.exists() and path.read_text(encoding="utf-8") != content:
        raise ValueError("existing report differs from content address")
    path.write_text(content, encoding="utf-8")
    return path


def _utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise argparse.ArgumentTypeError("시각은 UTC 오프셋을 포함해야 합니다")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description="한 CPI 사건의 Kalshi 다중 임계값 분포 감사")
    parser.add_argument("--event", required=True, help="예: KXCPI-26SEP")
    parser.add_argument(
        "--as-of", required=True, type=_utc_datetime, help="예: 2026-10-14T12:25:00Z"
    )
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "artifacts/raw")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/kalshi-cpi-curves")
    parser.add_argument("--request-interval", type=float, default=0.2)
    parser.add_argument("--max-isotonic-adjustment", type=float, default=0.05)
    args = parser.parse_args()
    store = ImmutableRawStore(args.raw_dir)
    with KalshiPublicClient(
        base_url=PRODUCTION_COMPAT_BASE_URL,
        timeout_seconds=30,
        retry_policy=RetryPolicy(max_attempts=4, initial_backoff_seconds=1),
    ) as client:
        report = audit_event_curve(
            client,
            store,
            event_ticker=args.event,
            as_of=args.as_of,
            request_interval_seconds=args.request_interval,
            max_isotonic_adjustment=args.max_isotonic_adjustment,
        )
    path = save_report(report, args.output)
    print(
        json.dumps(
            {
                "report": str(path),
                "status": report["status"],
                "candidate_threshold_markets": report["candidate_threshold_markets"],
                "quote_status_counts": report["quote_status_counts"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import UTC, datetime, timedelta
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
from shockgraph_analytics.evaluation import paired_interval  # noqa: E402
from shockgraph_collector.client import (  # noqa: E402
    PRODUCTION_COMPAT_BASE_URL,
    KalshiPublicClient,
    RetryPolicy,
)
from shockgraph_data_pipeline.raw_store import ImmutableRawStore  # noqa: E402

AUDIT_SCHEMA_VERSION = "kalshi-cpi-audit-v2"


def score_event_probabilities(
    events: list[dict[str, Any]], *, min_history: int = 10
) -> dict[str, Any]:
    if min_history < 1:
        raise ValueError("min_history must be positive")
    eligible = [
        event
        for event in events
        if event.get("status") == "eligible"
        and event.get("outcome") in ("yes", "no")
        and isinstance(event.get("probability_yes"), (int, float))
        and not isinstance(event.get("probability_yes"), bool)
        and math.isfinite(event["probability_yes"])
        and 0 <= event["probability_yes"] <= 1
    ]
    raw_losses = [
        (event["probability_yes"] - (event["outcome"] == "yes")) ** 2 for event in eligible
    ]
    comparisons: list[dict[str, float | str | int]] = []
    prior_outcomes: list[bool] = []
    for event in events:
        outcome = event.get("outcome")
        if outcome not in ("yes", "no"):
            continue
        probability = event.get("probability_yes")
        if (
            event.get("status") == "eligible"
            and isinstance(probability, (int, float))
            and not isinstance(probability, bool)
            and math.isfinite(probability)
            and 0 <= probability <= 1
            and len(prior_outcomes) >= min_history
        ):
            target = float(outcome == "yes")
            baseline = sum(prior_outcomes) / len(prior_outcomes)
            comparisons.append(
                {
                    "market_ticker": str(event.get("market_ticker", "")),
                    "prior_events": len(prior_outcomes),
                    "outcome_binary": int(target),
                    "probability_yes": probability,
                    "expanding_historical_probability": baseline,
                    "market_loss": (probability - target) ** 2,
                    "expanding_historical_loss": (baseline - target) ** 2,
                }
            )
        prior_outcomes.append(outcome == "yes")
    differences = [
        float(row["market_loss"]) - float(row["expanding_historical_loss"]) for row in comparisons
    ]
    return {
        "eligible_events": len(eligible),
        "raw_market_brier_all_eligible": math.fsum(raw_losses) / len(raw_losses)
        if raw_losses
        else None,
        "minimum_prior_events": min_history,
        "comparable_events": len(comparisons),
        "raw_market_brier": math.fsum(float(row["market_loss"]) for row in comparisons)
        / len(comparisons)
        if comparisons
        else None,
        "expanding_historical_brier": math.fsum(
            float(row["expanding_historical_loss"]) for row in comparisons
        )
        / len(comparisons)
        if comparisons
        else None,
        "mean_brier_difference": math.fsum(differences) / len(differences) if differences else None,
        "paired_event_bootstrap95": paired_interval(differences),
        "negative_difference_favors": "raw_market_probability",
        "comparisons": comparisons,
    }


def collect_market_tier(
    client: KalshiPublicClient,
    store: ImmutableRawStore,
    path: str,
    *,
    max_pages: int = 10,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cursor = ""
    seen: set[str] = set()
    for _ in range(max_pages):
        params: dict[str, Any] = {"series_ticker": "KXCPI", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
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
        rows.extend(markets)
        cursor = payload.get("cursor", "")
        if not isinstance(cursor, str):
            raise ValueError("cursor must be a string")
        if not cursor:
            return rows
        if cursor in seen:
            raise ValueError("repeated cursor")
        seen.add(cursor)
    raise RuntimeError("market inventory exceeded max_pages")


def audit_cpi(
    client: KalshiPublicClient,
    store: ImmutableRawStore,
    *,
    threshold_suffix: str = "-T0.3",
    request_interval_seconds: float = 0.2,
) -> dict[str, Any]:
    if not threshold_suffix.startswith("-T") or request_interval_seconds < 0:
        raise ValueError("invalid audit settings")
    historical = collect_market_tier(client, store, "/historical/markets")
    recent = collect_market_tier(client, store, "/markets")
    by_ticker = {
        row["ticker"]: (tier, row)
        for tier, rows in (("historical", historical), ("recent", recent))
        for row in rows
        if isinstance(row.get("ticker"), str)
    }
    candidates = sorted(
        (
            (tier, row)
            for tier, row in by_ticker.values()
            if row.get("result") in ("yes", "no") and row["ticker"].endswith(threshold_suffix)
        ),
        key=lambda pair: (pair[1].get("close_time", ""), pair[1]["ticker"]),
    )
    events: list[dict[str, Any]] = []
    for tier, market in candidates:
        ticker = market["ticker"]
        outcome = market["result"]
        close_time = market.get("close_time")
        if not isinstance(close_time, str):
            events.append(
                {"market_ticker": ticker, "outcome": outcome, "status": "invalid_close_time"}
            )
            continue
        cutoff = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
        if cutoff.utcoffset() != timedelta(0):
            events.append(
                {"market_ticker": ticker, "outcome": outcome, "status": "invalid_close_time"}
            )
            continue
        path = (
            f"/historical/markets/{ticker}/candlesticks"
            if tier == "historical"
            else f"/series/KXCPI/markets/{ticker}/candlesticks"
        )
        params = {
            "start_ts": int((cutoff - timedelta(hours=1)).timestamp()),
            "end_ts": int(cutoff.timestamp()),
            "period_interval": 1,
        }
        try:
            payload = client.get_json(path, params=params)
            store.save(
                payload,
                source="kalshi",
                endpoint=path,
                request_params=params,
                observed_at=client.clock(),
            )
            screen = inspect_pre_release_candles(payload, cutoff)
            status = (
                "eligible"
                if screen["near_release_candles"]
                else ("stale" if screen["eligible_candles"] else "no_eligible_candles")
            )
            latest_quote = screen.pop("latest_quote")
            row = {
                "event_ticker": market.get("event_ticker"),
                "market_ticker": ticker,
                "tier": tier,
                "cutoff_at": cutoff.isoformat(),
                "outcome": outcome,
                "status": status,
                **screen,
            }
            if status == "eligible" and latest_quote is not None:
                row.update(
                    probability_yes=latest_quote["yes_midpoint"],
                    quote_end_at=latest_quote["end_at"],
                    spread=latest_quote["spread"],
                    volume=latest_quote["volume"],
                )
            events.append(row)
        except (httpx.HTTPError, ValueError) as error:
            events.append(
                {
                    "event_ticker": market.get("event_ticker"),
                    "market_ticker": ticker,
                    "tier": tier,
                    "cutoff_at": cutoff.isoformat(),
                    "outcome": outcome,
                    "status": "access_error",
                    "error_type": type(error).__name__,
                    "http_status": error.response.status_code
                    if isinstance(error, httpx.HTTPStatusError)
                    else None,
                }
            )
        time.sleep(request_interval_seconds)
    counts = {
        status: sum(event["status"] == status for event in events)
        for status in ("eligible", "stale", "no_eligible_candles", "access_error")
    }
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "checked_at": datetime.now(UTC).isoformat(),
        "series_ticker": "KXCPI",
        "threshold_suffix": threshold_suffix,
        "market_counts": {"historical": len(historical), "recent": len(recent)},
        "settled_fixed_threshold_events": len(candidates),
        "status_counts": counts,
        "quality_rule": "one_minute,cutoff_or_earlier,positive_volume,spread<=0.10,fresh<=15m",
        "event_probability_comparison": score_event_probabilities(events),
        "events": events,
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Kalshi CPI 발표 직전 1분 캔들 커버리지 감사")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "artifacts/raw")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/kalshi-cpi-audit")
    parser.add_argument("--request-interval", type=float, default=0.2)
    args = parser.parse_args()
    store = ImmutableRawStore(args.raw_dir)
    with KalshiPublicClient(
        base_url=PRODUCTION_COMPAT_BASE_URL,
        timeout_seconds=30,
        retry_policy=RetryPolicy(max_attempts=4, initial_backoff_seconds=1),
    ) as client:
        report = audit_cpi(client, store, request_interval_seconds=args.request_interval)
    path = save_report(report, args.output)
    print(
        json.dumps(
            {
                "report": str(path),
                "settled_fixed_threshold_events": report["settled_fixed_threshold_events"],
                "status_counts": report["status_counts"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

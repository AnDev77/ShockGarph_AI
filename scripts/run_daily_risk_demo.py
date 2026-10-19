from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import asdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/domain"), str(ROOT / "packages/risk_engine")]

from shockgraph_domain.records import AssetPriceRecord  # noqa: E402
from shockgraph_risk.daily import (  # noqa: E402
    build_baseline_forecasts,
    label_forecasts,
    score_baselines,
)


def synthetic_prices() -> tuple[
    tuple[AssetPriceRecord, ...], tuple[date, ...], dict[date, datetime]
]:
    # Weekdays are a synthetic test calendar, not the actual US exchange schedule.
    sessions = tuple(
        date(2026, 1, 5) + timedelta(days=offset)
        for offset in range(250)
        if (date(2026, 1, 5) + timedelta(days=offset)).weekday() < 5
    )[:150]
    price = 100.0
    rows = []
    times = {}
    for index, session in enumerate(sessions):
        if index:
            price *= math.exp(0.012 * math.sin(index * 0.57) + 0.004 * math.cos(index * 0.19))
        observed_at = datetime.combine(session, time(21), tzinfo=UTC)
        rows.append(
            AssetPriceRecord(
                source="synthetic-demo",
                symbol="TLT",
                venue="XNAS",
                observed_at=observed_at,
                available_at=observed_at + timedelta(minutes=5),
                session_date=session,
                currency="USD",
                close=Decimal(str(price)),
                adjusted_close=Decimal(str(price)),
                raw_payload_hash=hashlib.sha256(
                    f"{session.isoformat()}:{price}".encode()
                ).hexdigest(),
            )
        )
        times[session] = observed_at + timedelta(minutes=10)
    return tuple(rows), sessions, times


def main() -> None:
    prices, sessions, times = synthetic_prices()
    reports = {}
    for horizon in (5, 20):
        forecasts = build_baseline_forecasts(prices, sessions, times, horizon=horizon)
        assert prices[-1].available_at is not None
        labeled = label_forecasts(
            forecasts, prices, sessions, evaluation_at=prices[-1].available_at
        )
        reports[str(horizon)] = asdict(
            score_baselines(labeled, holdout_start=times[sessions[100]])
        )
    print(
        json.dumps(
            {
                "status": "DEMO",
                "source": "synthetic prices and weekday-only calendar",
                "note": "Not an estimate of TLT performance; QLIKE uses a 1e-12 variance floor.",
                "reports": reports,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()

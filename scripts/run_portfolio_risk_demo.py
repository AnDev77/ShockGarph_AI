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

from shockgraph_domain.portfolio import validate_positions  # noqa: E402
from shockgraph_domain.records import AssetPriceRecord  # noqa: E402
from shockgraph_risk.portfolio import (  # noqa: E402
    build_portfolio_forecasts,
    label_portfolio_forecasts,
    score_portfolio_baselines,
)


def synthetic_panel() -> tuple[
    dict[str, tuple[AssetPriceRecord, ...]], tuple[date, ...], dict[date, datetime]
]:
    # This weekday-only calendar deliberately does not represent US exchange holidays.
    start = date(2025, 1, 6)
    sessions = tuple(
        start + timedelta(days=offset)
        for offset in range(330)
        if (start + timedelta(days=offset)).weekday() < 5
    )[:220]
    prices = {"SPY": 100.0, "TLT": 100.0}
    panel: dict[str, list[AssetPriceRecord]] = {"SPY": [], "TLT": []}
    predictions = {}
    for index, session in enumerate(sessions):
        if index:
            equity = 0.012 * math.sin(index * 0.53) + 0.003 * math.cos(index * 0.19)
            bond = (-0.6 if index < 110 else 0.5) * equity + 0.004 * math.cos(index * 0.47)
            prices["SPY"] *= math.exp(equity)
            prices["TLT"] *= math.exp(bond)
        observed_at = datetime.combine(session, time(21), tzinfo=UTC)
        for symbol, value in prices.items():
            panel[symbol].append(
                AssetPriceRecord(
                    source="synthetic-portfolio-demo",
                    symbol=symbol,
                    venue="XNAS",
                    observed_at=observed_at,
                    available_at=observed_at + timedelta(minutes=5),
                    session_date=session,
                    currency="USD",
                    close=Decimal(str(value)),
                    adjusted_close=Decimal(str(value)),
                    raw_payload_hash=hashlib.sha256(
                        f"{symbol}:{session.isoformat()}:{value}".encode()
                    ).hexdigest(),
                )
            )
        predictions[session] = observed_at + timedelta(minutes=10)
    return {symbol: tuple(rows) for symbol, rows in panel.items()}, sessions, predictions


def main() -> None:
    panel, sessions, predictions = synthetic_panel()
    portfolio = validate_positions(
        [{"symbol": "SPY", "weight": 0.6}, {"symbol": "TLT", "weight": 0.4}]
    )
    reports = {}
    for horizon in (5, 20):
        forecasts = build_portfolio_forecasts(
            panel, sessions, predictions, portfolio, horizon=horizon
        )
        evaluation_at = panel["TLT"][-1].available_at
        assert evaluation_at is not None
        labeled = label_portfolio_forecasts(
            forecasts, panel, sessions, portfolio, evaluation_at=evaluation_at
        )
        reports[str(horizon)] = asdict(
            score_portfolio_baselines(labeled, holdout_start=predictions[sessions[120]])
        )
    print(
        json.dumps(
            {
                "status": "DEMO",
                "source": "synthetic SPY/TLT prices and weekday-only calendar",
                "assumption": "USD daily-rebalanced weights; no trading costs",
                "note": (
                    "No actual ETF data, empirical performance, or portfolio tail-loss estimate."
                ),
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

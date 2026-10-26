"""One ETF's historical state, with an optional two-asset total change calculation."""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from shockgraph_risk.exploratory_history import HistoryPrice


@dataclass(frozen=True, slots=True)
class AssetHistorySummary:
    symbol: str
    first_session: date
    last_session: date
    observation_count: int
    period_return: float
    recent_five_session_return: float
    recent_twenty_session_return: float
    recent_daily_volatility: float
    volatility_window_count: int
    recent_volatility_percentile: float
    period_max_drawdown: float
    calendar_validated: bool = False
    public_display_allowed: bool = False
    is_prediction: bool = False


@dataclass(frozen=True, slots=True)
class WeightedTotalChange:
    start_session: date
    end_session: date
    first_symbol: str
    second_symbol: str
    first_weight: float
    total_return: float
    basis: str = "initial_weights_buy_and_hold"
    public_display_allowed: bool = False
    is_prediction: bool = False


def analyze_asset_history(
    symbol: str,
    prices: Sequence[HistoryPrice],
    *,
    trailing_window: int = 60,
    volatility_window: int = 20,
) -> AssetHistorySummary:
    """Describe one price history. All calculations end at the last input date."""
    if not symbol.strip():
        raise ValueError("symbol is required")
    if trailing_window < 20 or volatility_window < 2 or volatility_window > trailing_window:
        raise ValueError("invalid trailing or volatility window")
    if len(prices) <= trailing_window:
        raise ValueError("insufficient price observations for the requested window")
    days = [row.session_date for row in prices]
    if any(later <= earlier for earlier, later in zip(days, days[1:], strict=False)):
        raise ValueError("session dates must be unique and increasing")
    closes = [row.adjusted_close for row in prices]
    if any(not math.isfinite(value) or value <= 0 for value in closes):
        raise ValueError("adjusted closes must be positive and finite")

    daily_returns = [later / earlier - 1 for earlier, later in
                     zip(closes, closes[1:], strict=False)]
    rolling_volatilities = [
        statistics.stdev(daily_returns[end - volatility_window:end])
        for end in range(volatility_window, len(daily_returns) + 1)
    ]
    recent_volatility = rolling_volatilities[-1]
    percentile = (sum(value <= recent_volatility for value in rolling_volatilities)
                  / len(rolling_volatilities))
    recent_closes = closes[-(trailing_window + 1):]
    peak, max_drawdown = recent_closes[0], 0.0
    for close in recent_closes[1:]:
        peak = max(peak, close)
        max_drawdown = max(max_drawdown, 1 - close / peak)
    return AssetHistorySummary(
        symbol=symbol.strip().upper(),
        first_session=days[-(trailing_window + 1)],
        last_session=days[-1],
        observation_count=len(prices),
        period_return=closes[-1] / recent_closes[0] - 1,
        recent_five_session_return=closes[-1] / closes[-6] - 1,
        recent_twenty_session_return=closes[-1] / closes[-21] - 1,
        recent_daily_volatility=recent_volatility,
        volatility_window_count=len(rolling_volatilities),
        recent_volatility_percentile=percentile,
        period_max_drawdown=max_drawdown,
    )


def weighted_total_change(
    first: AssetHistorySummary,
    second: AssetHistorySummary,
    *,
    first_weight: float,
) -> WeightedTotalChange:
    """Period change from initial weights without rebalancing or cash flows."""
    if not math.isfinite(first_weight) or not 0 <= first_weight <= 1:
        raise ValueError("first_weight must be between zero and one")
    if first.symbol == second.symbol:
        raise ValueError("two different assets are required")
    if (first.first_session, first.last_session) != (second.first_session, second.last_session):
        raise ValueError("both assets need the same start and end sessions")
    return WeightedTotalChange(
        start_session=first.first_session,
        end_session=first.last_session,
        first_symbol=first.symbol,
        second_symbol=second.symbol,
        first_weight=first_weight,
        total_return=first_weight * first.period_return
        + (1 - first_weight) * second.period_return,
    )

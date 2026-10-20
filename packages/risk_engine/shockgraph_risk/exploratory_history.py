"""Private exploratory volatility comparison on one currently downloaded price history.

The input has no historical publication timestamps. Results cannot establish that the
same adjusted prices were available when each historical forecast would have been made.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from shockgraph_risk.daily import _paired_block_interval


@dataclass(frozen=True, slots=True)
class HistoryPrice:
    session_date: date
    adjusted_close: float


@dataclass(frozen=True, slots=True)
class ExploratoryHorizon:
    horizon: int
    status: str
    sample_size: int
    nonoverlapping_window_count: int
    first_prediction_date: date | None
    last_prediction_date: date | None
    trailing_mae: float | None
    ewma_mae: float | None
    trailing_qlike: float | None
    ewma_qlike: float | None
    ewma_minus_trailing_mae: float | None
    paired_mae_ci: tuple[float, float] | None


def evaluate_adjusted_history(
    prices: Sequence[HistoryPrice],
    *,
    holdout_start: date,
    horizons: tuple[int, ...] = (5, 20),
    bootstrap_repeats: int = 1000,
) -> tuple[ExploratoryHorizon, ...]:
    """Compare trailing and EWMA only after complete future windows exist.

    Dates identify observations, not their original availability. This is an
    exploratory retrospective calculation, not a point-in-time backtest.
    """
    if not horizons or len(set(horizons)) != len(horizons) or any(h < 2 for h in horizons):
        raise ValueError("horizons must be unique and at least two sessions")
    if bootstrap_repeats < 100:
        raise ValueError("bootstrap_repeats must be at least 100")
    if not prices:
        raise ValueError("price history is empty")
    dates = [row.session_date for row in prices]
    if any(later <= earlier for earlier, later in zip(dates, dates[1:], strict=False)):
        raise ValueError("price dates must be unique and increasing")
    if any(not math.isfinite(row.adjusted_close) or row.adjusted_close <= 0 for row in prices):
        raise ValueError("adjusted closes must be positive and finite")
    if holdout_start <= dates[0] or holdout_start > dates[-1]:
        raise ValueError("holdout_start must follow the first date and not exceed the last")

    logs = [math.log(row.adjusted_close) for row in prices]
    squares = [(current - previous) ** 2 for previous, current in zip(logs, logs[1:], strict=False)]
    reports = []
    for horizon in horizons:
        alpha = 2 / (horizon + 1)
        ewma_variance = math.fsum(squares[:horizon]) / horizon
        trailing_errors: list[float] = []
        ewma_errors: list[float] = []
        trailing_qlike: list[float] = []
        ewma_qlike: list[float] = []
        forecast_dates: list[date] = []
        for index in range(horizon, len(prices) - horizon):
            if index > horizon:
                ewma_variance = alpha * squares[index - 1] + (1 - alpha) * ewma_variance
            if dates[index] < holdout_start:
                continue
            trailing_variance = math.fsum(squares[index - horizon : index]) / horizon
            actual_variance = math.fsum(squares[index : index + horizon]) / horizon
            trailing_errors.append(abs(math.sqrt(trailing_variance) - math.sqrt(actual_variance)))
            ewma_errors.append(abs(math.sqrt(ewma_variance) - math.sqrt(actual_variance)))
            trailing_qlike.append(
                math.log(max(trailing_variance, 1e-12))
                + actual_variance / max(trailing_variance, 1e-12)
            )
            ewma_qlike.append(
                math.log(max(ewma_variance, 1e-12))
                + actual_variance / max(ewma_variance, 1e-12)
            )
            forecast_dates.append(dates[index])

        count = len(forecast_dates)
        nonoverlap = count // horizon
        if nonoverlap < 2:
            reports.append(
                ExploratoryHorizon(
                    horizon, "insufficient_future_windows", count, nonoverlap,
                    forecast_dates[0] if count else None,
                    forecast_dates[-1] if count else None,
                    None, None, None, None, None, None,
                )
            )
            continue
        differences = [new - old for new, old in zip(ewma_errors, trailing_errors, strict=True)]
        reports.append(
            ExploratoryHorizon(
                horizon=horizon,
                status="exploratory_current_history_only",
                sample_size=count,
                nonoverlapping_window_count=nonoverlap,
                first_prediction_date=forecast_dates[0],
                last_prediction_date=forecast_dates[-1],
                trailing_mae=math.fsum(trailing_errors) / count,
                ewma_mae=math.fsum(ewma_errors) / count,
                trailing_qlike=math.fsum(trailing_qlike) / count,
                ewma_qlike=math.fsum(ewma_qlike) / count,
                ewma_minus_trailing_mae=math.fsum(differences) / count,
                paired_mae_ci=_paired_block_interval(
                    differences, block_length=horizon, repeats=bootstrap_repeats, seed=0
                ),
            )
        )
    return tuple(reports)

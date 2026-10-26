"""Private, retrospective GARCH comparison on one current adjusted-price history.

The historical adjusted-price vintages and their first available times are unknown.
These observations can illustrate forecast behavior but cannot validate a live signal.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from shockgraph_risk.daily import _paired_block_interval
from shockgraph_risk.exploratory_history import HistoryPrice
from shockgraph_risk.garch import GarchParameters, fit_garch_11, forecast_garch_11


@dataclass(frozen=True, slots=True)
class ExploratoryGarchPoint:
    session_date: date
    observed_volatility: float
    trailing_volatility: float
    ewma_volatility: float
    garch_volatility: float


@dataclass(frozen=True, slots=True)
class ExploratoryGarchReport:
    horizon: int
    status: str
    training_return_count: int
    last_training_session: date | None
    sample_size: int
    nonoverlapping_window_count: int
    first_prediction_date: date | None
    last_prediction_date: date | None
    trailing_mae: float | None
    ewma_mae: float | None
    garch_mae: float | None
    trailing_qlike: float | None
    ewma_qlike: float | None
    garch_qlike: float | None
    garch_minus_ewma_mae_ci: tuple[float, float] | None
    parameters: GarchParameters | None
    points: tuple[ExploratoryGarchPoint, ...]
    public_performance_allowed: bool = False


def _qlike(predicted: float, actual: float) -> float:
    variance = max(predicted * predicted, 1e-12)
    return math.log(variance) + actual * actual / variance


def evaluate_exploratory_garch(
    prices: Sequence[HistoryPrice],
    *,
    holdout_start: date,
    horizons: tuple[int, ...] = (5, 20),
    min_training_returns: int = 100,
    bootstrap_repeats: int = 1000,
) -> tuple[ExploratoryGarchReport, ...]:
    """Fit once pre-holdout and score GARCH and simple baselines on shared dates."""
    if not horizons or len(set(horizons)) != len(horizons) or any(h < 2 for h in horizons):
        raise ValueError("horizons must be unique and at least two sessions")
    if min_training_returns < 30 or bootstrap_repeats < 100:
        raise ValueError("at least 30 training returns and 100 bootstraps are required")
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
    returns = tuple(later - earlier for earlier, later in zip(logs, logs[1:], strict=False))
    squares = tuple(value * value for value in returns)
    split = next(index for index, day in enumerate(dates) if day >= holdout_start)
    training_returns = returns[: split - 1]
    parameters = None
    fit_reason = None
    if len(training_returns) < min_training_returns:
        fit_reason = "insufficient_pre_holdout_returns"
    else:
        try:
            parameters = fit_garch_11(training_returns, min_returns=min_training_returns)
        except ValueError as error:
            if str(error) not in {"degenerate_training_returns", "garch_fit_did_not_converge"}:
                raise
            fit_reason = str(error)

    reports = []
    for horizon in horizons:
        eligible = [index for index in range(horizon, len(prices) - horizon)
                    if dates[index] >= holdout_start]
        count = len(eligible)
        blocks = count // horizon
        status = fit_reason or ("insufficient_future_windows" if blocks < 2 else
                                "exploratory_current_history_only")
        blocked = ExploratoryGarchReport(
            horizon=horizon, status=status, training_return_count=len(training_returns),
            last_training_session=dates[split - 1], sample_size=count,
            nonoverlapping_window_count=blocks,
            first_prediction_date=dates[eligible[0]] if eligible else None,
            last_prediction_date=dates[eligible[-1]] if eligible else None,
            trailing_mae=None, ewma_mae=None, garch_mae=None,
            trailing_qlike=None, ewma_qlike=None, garch_qlike=None,
            garch_minus_ewma_mae_ci=None, parameters=parameters, points=(),
        )
        if status != "exploratory_current_history_only":
            reports.append(blocked)
            continue
        assert parameters is not None
        alpha = 2 / (horizon + 1)
        ewma_variance = math.fsum(squares[:horizon]) / horizon
        errors: dict[str, list[float]] = {name: [] for name in ("trailing", "ewma", "garch")}
        qlikes: dict[str, list[float]] = {name: [] for name in errors}
        points = []
        for index in range(horizon, len(prices) - horizon):
            if index > horizon:
                ewma_variance = alpha * squares[index - 1] + (1 - alpha) * ewma_variance
            if dates[index] < holdout_start:
                continue
            actual = math.sqrt(math.fsum(squares[index : index + horizon]) / horizon)
            predictions = {
                "trailing": math.sqrt(math.fsum(squares[index - horizon : index]) / horizon),
                "ewma": math.sqrt(ewma_variance),
                "garch": forecast_garch_11(returns[:index], parameters, horizon=horizon),
            }
            points.append(ExploratoryGarchPoint(
                session_date=dates[index], observed_volatility=actual,
                trailing_volatility=predictions["trailing"],
                ewma_volatility=predictions["ewma"], garch_volatility=predictions["garch"],
            ))
            for name, predicted in predictions.items():
                errors[name].append(abs(predicted - actual))
                qlikes[name].append(_qlike(predicted, actual))
        differences = [new - old for new, old in zip(errors["garch"], errors["ewma"],
                                                       strict=True)]
        reports.append(ExploratoryGarchReport(
            horizon=horizon, status=status, training_return_count=len(training_returns),
            last_training_session=dates[split - 1], sample_size=count,
            nonoverlapping_window_count=blocks,
            first_prediction_date=dates[eligible[0]], last_prediction_date=dates[eligible[-1]],
            trailing_mae=math.fsum(errors["trailing"]) / count,
            ewma_mae=math.fsum(errors["ewma"]) / count,
            garch_mae=math.fsum(errors["garch"]) / count,
            trailing_qlike=math.fsum(qlikes["trailing"]) / count,
            ewma_qlike=math.fsum(qlikes["ewma"]) / count,
            garch_qlike=math.fsum(qlikes["garch"]) / count,
            garch_minus_ewma_mae_ci=_paired_block_interval(
                differences, block_length=horizon, repeats=bootstrap_repeats, seed=0
            ),
            parameters=parameters, points=tuple(points),
        ))
    return tuple(reports)

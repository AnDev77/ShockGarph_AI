"""Exploratory expanding-window monthly refits from one unverified price vintage.

At each month's first forecast close, refit only on returns observable through
that close. Keep parameters fixed through that month while filtering new returns.
The entire historical adjusted-close vintage is current, not contemporaneous.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from shockgraph_risk.daily import _paired_block_interval
from shockgraph_risk.exploratory_garch import ExploratoryGarchReport
from shockgraph_risk.exploratory_history import HistoryPrice
from shockgraph_risk.garch import GarchParameters, fit_garch_11, forecast_garch_11
from shockgraph_risk.gjr_garch import GjrParameters, fit_gjr_garch_11, forecast_gjr_garch_11


@dataclass(frozen=True, slots=True)
class MonthlyRefit:
    month: str
    training_return_count: int
    last_training_session: date
    garch_parameters: GarchParameters
    gjr_parameters: GjrParameters


@dataclass(frozen=True, slots=True)
class MonthlyRefitPoint:
    session_date: date
    observed_volatility: float
    garch_volatility: float
    gjr_volatility: float


@dataclass(frozen=True, slots=True)
class MonthlyRefitReport:
    horizon: int
    status: str
    sample_size: int
    refit_months: tuple[MonthlyRefit, ...]
    garch_mae: float | None
    gjr_mae: float | None
    gjr_minus_monthly_garch_mae_ci: tuple[float, float] | None
    gjr_minus_static_gjr_mae_ci: tuple[float, float] | None
    points: tuple[MonthlyRefitPoint, ...]
    public_performance_allowed: bool = False


def evaluate_monthly_garch_refit(
    prices: Sequence[HistoryPrice],
    *,
    static_reports: Sequence[ExploratoryGarchReport],
    holdout_start: date,
    bootstrap_repeats: int = 1000,
    min_training_returns: int = 100,
) -> tuple[MonthlyRefitReport, ...]:
    """Compare monthly updating with static forecasts on exactly the same dates."""
    if bootstrap_repeats < 100 or min_training_returns < 30 or not static_reports:
        raise ValueError("monthly refit requires models, training returns and bootstraps")
    dates = [row.session_date for row in prices]
    if not dates or any(b <= a for a, b in zip(dates, dates[1:], strict=False)):
        raise ValueError("price dates must be unique and increasing")
    if any(not math.isfinite(row.adjusted_close) or row.adjusted_close <= 0 for row in prices):
        raise ValueError("adjusted closes must be positive and finite")
    indices = {day: index for index, day in enumerate(dates)}
    logs = [math.log(row.adjusted_close) for row in prices]
    returns = tuple(b - a for a, b in zip(logs, logs[1:], strict=False))
    cache: dict[str, MonthlyRefit] = {}
    reports = []
    for baseline in static_reports:
        if baseline.status != "exploratory_current_history_only":
            reports.append(MonthlyRefitReport(
                horizon=baseline.horizon, status=baseline.status,
                sample_size=baseline.sample_size, refit_months=(),
                garch_mae=None, gjr_mae=None,
                gjr_minus_monthly_garch_mae_ci=None,
                gjr_minus_static_gjr_mae_ci=None, points=(),
            ))
            continue
        if baseline.gjr_parameters is None or len(baseline.points) != baseline.sample_size:
            reports.append(MonthlyRefitReport(
                horizon=baseline.horizon, status="static_gjr_unavailable",
                sample_size=baseline.sample_size, refit_months=(),
                garch_mae=None, gjr_mae=None,
                gjr_minus_monthly_garch_mae_ci=None,
                gjr_minus_static_gjr_mae_ci=None, points=(),
            ))
            continue
        rows: list[MonthlyRefitPoint] = []
        monthly_fits = []
        used_months: set[str] = set()
        failure = None
        for static_point in baseline.points:
            day = static_point.session_date
            index = indices.get(day)
            if index is None or day < holdout_start or index + baseline.horizon >= len(prices):
                raise ValueError("static and monthly forecast dates differ")
            actual = math.sqrt(math.fsum(
                value * value for value in returns[index:index + baseline.horizon]
            ) / baseline.horizon)
            if not math.isclose(actual, static_point.observed_volatility, abs_tol=1e-12):
                raise ValueError("static and monthly forecast labels differ")
            month = day.strftime("%Y-%m")
            if month not in cache:
                training_returns = returns[:index]
                try:
                    garch = fit_garch_11(training_returns, min_returns=min_training_returns)
                    gjr = fit_gjr_garch_11(training_returns, min_returns=min_training_returns)
                except ValueError as error:
                    failure = f"monthly_refit_failed:{month}:{error}"
                    break
                cache[month] = MonthlyRefit(
                    month=month, training_return_count=len(training_returns),
                    last_training_session=day, garch_parameters=garch, gjr_parameters=gjr,
                )
            params = cache[month]
            if month not in used_months:
                monthly_fits.append(params)
                used_months.add(month)
            rows.append(MonthlyRefitPoint(
                session_date=day, observed_volatility=actual,
                garch_volatility=forecast_garch_11(
                    returns[:index], params.garch_parameters, horizon=baseline.horizon,
                ),
                gjr_volatility=forecast_gjr_garch_11(
                    returns[:index], params.gjr_parameters, horizon=baseline.horizon,
                ),
            ))
        if failure:
            reports.append(MonthlyRefitReport(
                horizon=baseline.horizon, status=failure, sample_size=baseline.sample_size,
                refit_months=tuple(monthly_fits), garch_mae=None, gjr_mae=None,
                gjr_minus_monthly_garch_mae_ci=None,
                gjr_minus_static_gjr_mae_ci=None, points=(),
            ))
            continue
        if len(rows) != baseline.sample_size:
            raise ValueError("monthly refit sample size differs from static model")
        garch_errors = [abs(point.garch_volatility - point.observed_volatility)
                        for point in rows]
        gjr_errors = [abs(point.gjr_volatility - point.observed_volatility)
                      for point in rows]
        static_gjr_errors = [abs(point.gjr_volatility - point.observed_volatility)
                             for point in baseline.points if point.gjr_volatility is not None]
        if len(static_gjr_errors) != len(rows):
            raise ValueError("static GJR predictions are incomplete")
        reports.append(MonthlyRefitReport(
            horizon=baseline.horizon, status="exploratory_current_history_only",
            sample_size=len(rows), refit_months=tuple(monthly_fits),
            garch_mae=math.fsum(garch_errors) / len(rows),
            gjr_mae=math.fsum(gjr_errors) / len(rows),
            gjr_minus_monthly_garch_mae_ci=_paired_block_interval(
                [new - old for new, old in zip(gjr_errors, garch_errors, strict=True)],
                block_length=baseline.horizon, repeats=bootstrap_repeats, seed=0,
            ),
            gjr_minus_static_gjr_mae_ci=_paired_block_interval(
                [new - old for new, old in zip(gjr_errors, static_gjr_errors, strict=True)],
                block_length=baseline.horizon, repeats=bootstrap_repeats, seed=0,
            ), points=tuple(rows),
        ))
    return tuple(reports)

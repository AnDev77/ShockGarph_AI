from __future__ import annotations

import math
from datetime import date, timedelta

import pytest
from shockgraph_risk.exploratory_garch import evaluate_exploratory_garch
from shockgraph_risk.exploratory_history import HistoryPrice
from shockgraph_risk.monthly_garch_refit import evaluate_monthly_garch_refit


def _prices() -> tuple[HistoryPrice, ...]:
    rows = []
    day = date(2024, 1, 2)
    while len(rows) < 240:
        if day.weekday() < 5:
            index = len(rows)
            rows.append(HistoryPrice(day, 100 * math.exp(
                index * 0.0003 + 0.04 * math.sin(index / 8) + 0.012 * math.cos(index / 3)
            )))
        day += timedelta(days=1)
    return tuple(rows)


def test_monthly_refit_uses_same_dates_and_only_known_returns() -> None:
    prices = _prices()
    split = prices[155].session_date
    static = evaluate_exploratory_garch(
        prices, holdout_start=split, bootstrap_repeats=100,
    )
    reports = evaluate_monthly_garch_refit(
        prices, static_reports=static, holdout_start=split, bootstrap_repeats=100,
    )
    for report, old in zip(reports, static, strict=True):
        assert report.status == "exploratory_current_history_only"
        assert report.public_performance_allowed is False
        assert len(report.points) == len(old.points) == report.sample_size
        assert [point.session_date for point in report.points] == [
            point.session_date for point in old.points
        ]
        assert [point.observed_volatility for point in report.points] == pytest.approx(
            [point.observed_volatility for point in old.points]
        )
        assert report.gjr_minus_monthly_garch_mae_ci is not None
        assert report.gjr_minus_static_gjr_mae_ci is not None
        assert report.refit_months[0].training_return_count == 155
        assert report.refit_months[0].last_training_session == prices[155].session_date

    # Revising a later close cannot alter an earlier month's fitted coefficients
    # or a forecast made at the first holdout close.
    revised = (*prices[:-1], HistoryPrice(prices[-1].session_date,
                                         prices[-1].adjusted_close * 1.25))
    changed = evaluate_monthly_garch_refit(
        revised, static_reports=evaluate_exploratory_garch(
            revised, holdout_start=split, bootstrap_repeats=100,
        ), holdout_start=split, bootstrap_repeats=100,
    )
    for before, after in zip(reports, changed, strict=True):
        assert before.refit_months[0] == after.refit_months[0]
        assert before.points[0] == after.points[0]


def test_blocked_static_comparison_does_not_claim_refit_performance() -> None:
    prices = _prices()[:175]
    start = prices[155].session_date
    static = evaluate_exploratory_garch(
        prices, holdout_start=start, bootstrap_repeats=100,
    )
    reports = evaluate_monthly_garch_refit(
        prices, static_reports=static, holdout_start=start, bootstrap_repeats=100,
    )
    blocked = next(report for report in reports if report.horizon == 20)
    assert blocked.status == "insufficient_future_windows"
    assert blocked.gjr_mae is None and not blocked.points

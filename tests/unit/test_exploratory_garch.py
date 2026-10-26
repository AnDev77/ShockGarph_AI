from __future__ import annotations

from datetime import date, timedelta

import pytest
from shockgraph_risk.exploratory_garch import evaluate_exploratory_garch
from shockgraph_risk.exploratory_history import HistoryPrice, evaluate_adjusted_history


def _history(length: int = 195) -> tuple[HistoryPrice, ...]:
    rows = []
    current = 100.0
    day = date(2024, 1, 2)
    while len(rows) < length:
        if day.weekday() < 5:
            change = (0.012 if len(rows) % 5 else -0.019) * (
                1.5 if len(rows) > 150 else 1.0
            )
            current *= 1 + change
            rows.append(HistoryPrice(day, current))
        day += timedelta(days=1)
    return tuple(rows)


def test_garch_uses_same_holdout_labels_as_existing_price_baseline() -> None:
    prices = _history()
    split = prices[120].session_date
    reports = evaluate_exploratory_garch(
        prices, holdout_start=split, min_training_returns=100, bootstrap_repeats=100
    )
    original = evaluate_adjusted_history(
        prices, holdout_start=split, bootstrap_repeats=100
    )
    for report, baseline in zip(reports, original, strict=True):
        assert report.status == "exploratory_current_history_only"
        assert report.public_performance_allowed is False
        assert report.training_return_count == 119
        assert report.sample_size == baseline.sample_size
        assert report.first_prediction_date == baseline.first_prediction_date
        assert report.last_prediction_date == baseline.last_prediction_date
        assert report.ewma_mae == pytest.approx(baseline.ewma_mae)
        assert report.trailing_mae == pytest.approx(baseline.trailing_mae)
        assert report.garch_mae is not None
        assert report.gjr_mae is not None
        assert report.gjr_minus_garch_mae_ci is not None
        assert report.gjr_parameters is not None
        assert report.garch_minus_ewma_mae_ci is not None
        assert all(point.garch_volatility > 0 for point in report.points)
        assert all(point.gjr_volatility is not None and point.gjr_volatility > 0
                   for point in report.points)


def test_future_revision_cannot_refit_garch_and_short_history_is_blocked() -> None:
    prices = _history()
    split = prices[120].session_date
    original = evaluate_exploratory_garch(prices, holdout_start=split)
    changed = (*prices[:-1], HistoryPrice(prices[-1].session_date,
                                         prices[-1].adjusted_close * 1.5))
    revised = evaluate_exploratory_garch(changed, holdout_start=split)
    for before, after in zip(original, revised, strict=True):
        assert before.parameters == after.parameters
        assert before.gjr_parameters == after.gjr_parameters
        assert before.training_return_count == after.training_return_count
        assert before.garch_mae != after.garch_mae
        assert before.gjr_mae != after.gjr_mae

    blocked = evaluate_exploratory_garch(
        prices[:135], holdout_start=prices[50].session_date,
        min_training_returns=100,
    )
    assert all(row.status == "insufficient_pre_holdout_returns" for row in blocked)
    assert all(row.garch_mae is None and not row.points for row in blocked)

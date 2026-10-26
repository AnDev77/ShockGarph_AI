from __future__ import annotations

import math
from datetime import date, timedelta

import pytest
from shockgraph_risk.exploratory_history import HistoryPrice, evaluate_adjusted_history
from shockgraph_risk.exploratory_model import compare_price_only_model


def history(returns: list[float]) -> list[HistoryPrice]:
    prices = [100.0]
    for value in returns:
        prices.append(prices[-1] * math.exp(value))
    return [
        HistoryPrice(date(2024, 1, 1) + timedelta(days=i), price)
        for i, price in enumerate(prices)
    ]


def test_training_parameters_cannot_change_when_only_holdout_prices_change() -> None:
    unchanged = history([0.01] * 280)
    future_shock = history([0.01] * 150 + [0.05] * 130)
    start = unchanged[150].session_date

    original = compare_price_only_model(unchanged, holdout_start=start)
    changed = compare_price_only_model(future_shock, holdout_start=start)

    for base, shock in zip(original, changed, strict=True):
        assert base.status == shock.status == "exploratory_current_history_only"
        assert base.coefficients == shock.coefficients
        assert base.last_training_label_date == unchanged[149].session_date
        assert base.last_training_label_date is not None
        assert base.last_training_label_date < start
        assert base.holdout_count == shock.holdout_count
        assert base.ridge_mae is not None and shock.ridge_mae is not None
        assert shock.ridge_mae > base.ridge_mae


def test_candidate_and_baselines_share_exact_holdout_rows() -> None:
    rows = history([0.01 + 0.005 * math.sin(i / 7) for i in range(280)])
    start = rows[150].session_date
    baselines = evaluate_adjusted_history(rows, holdout_start=start)
    candidates = compare_price_only_model(rows, holdout_start=start)

    for baseline, candidate in zip(baselines, candidates, strict=True):
        assert candidate.holdout_count == baseline.sample_size
        assert candidate.first_holdout_date == baseline.first_prediction_date
        assert candidate.last_holdout_date == baseline.last_prediction_date
        assert candidate.trailing_mae == pytest.approx(baseline.trailing_mae)
        assert candidate.ewma_mae == pytest.approx(baseline.ewma_mae)
        assert candidate.coefficients is not None and len(candidate.coefficients) == 4
        assert len(candidate.points) == candidate.holdout_count
        assert candidate.points[0].session_date == candidate.first_holdout_date
        assert candidate.ridge_mae == pytest.approx(sum(
            abs(point.ridge_volatility - point.observed_volatility)
            for point in candidate.points
        ) / candidate.holdout_count)


def test_training_shortage_suppresses_all_candidate_metrics() -> None:
    rows = history([0.0] * 150)
    result = compare_price_only_model(rows, holdout_start=rows[50].session_date)[1]

    assert result.status == "insufficient_training_or_holdout"
    assert result.training_count < 100
    assert result.coefficients is None
    assert result.trailing_mae is None
    assert result.ridge_mae is None
    assert result.points == ()

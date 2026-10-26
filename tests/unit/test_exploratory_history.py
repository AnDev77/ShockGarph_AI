from __future__ import annotations

import math
from datetime import date, timedelta

import pytest
from shockgraph_risk.exploratory_history import HistoryPrice, evaluate_adjusted_history


def history(returns: list[float]) -> list[HistoryPrice]:
    values = [100.0]
    for daily_return in returns:
        values.append(values[-1] * math.exp(daily_return))
    return [
        HistoryPrice(date(2024, 1, 1) + timedelta(days=index), value)
        for index, value in enumerate(values)
    ]


def test_constant_returns_have_zero_error_on_complete_future_windows() -> None:
    rows = history([0.01] * 80)
    five, twenty = evaluate_adjusted_history(rows, holdout_start=rows[30].session_date)

    assert (five.sample_size, twenty.sample_size) == (46, 31)
    assert five.nonoverlapping_window_count == 9
    assert twenty.nonoverlapping_window_count == 1
    assert five.trailing_mae == pytest.approx(0, abs=1e-14)
    assert five.ewma_mae == pytest.approx(0, abs=1e-14)
    assert five.last_prediction_date == rows[75].session_date
    assert twenty.status == "insufficient_future_windows"
    assert twenty.trailing_mae is None


def test_future_shock_increases_forecast_error() -> None:
    before = history([0.01] * 80)
    after = history([0.01] * 40 + [0.04] * 40)
    start = before[30].session_date

    base = evaluate_adjusted_history(before, holdout_start=start, horizons=(5,))[0]
    shock = evaluate_adjusted_history(after, holdout_start=start, horizons=(5,))[0]

    assert base.sample_size == shock.sample_size
    assert shock.trailing_mae is not None and shock.trailing_mae > 0
    assert shock.first_prediction_date == start


def test_invalid_history_and_insufficient_futures_do_not_produce_scores() -> None:
    rows = history([0.01] * 32)
    holdout_start = rows[24].session_date
    short = evaluate_adjusted_history(rows, holdout_start=holdout_start, horizons=(5,))[0]
    assert short.sample_size == 4
    assert short.status == "insufficient_future_windows"
    assert short.ewma_mae is None

    with pytest.raises(ValueError, match="unique and increasing"):
        evaluate_adjusted_history([rows[0], rows[0]], holdout_start=holdout_start)
    with pytest.raises(ValueError, match="positive and finite"):
        bad = rows.copy()
        bad[20] = HistoryPrice(bad[20].session_date, float("nan"))
        evaluate_adjusted_history(bad, holdout_start=holdout_start)

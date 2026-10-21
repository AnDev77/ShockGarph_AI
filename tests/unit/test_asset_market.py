from __future__ import annotations

from datetime import date, timedelta
from math import prod

import pytest
from shockgraph_risk.asset_market import analyze_asset_history, weighted_total_change
from shockgraph_risk.exploratory_history import HistoryPrice


def history(returns: list[float], *, offset: int = 0) -> tuple[HistoryPrice, ...]:
    price = 100.0
    rows = [HistoryPrice(date(2026, 1, 1) + timedelta(days=offset), price)]
    for index, value in enumerate(returns, 1):
        price *= 1 + value
        rows.append(HistoryPrice(date(2026, 1, 1) + timedelta(days=offset + index), price))
    return tuple(rows)


def test_single_asset_summary_uses_only_its_own_prices() -> None:
    spy_returns = [0.02, -0.03, 0.01, -0.02] * 20
    report = analyze_asset_history("SPY", history(spy_returns))

    assert report.first_session == date(2026, 1, 21)
    assert report.recent_five_session_return == pytest.approx(
        prod(1 + value for value in spy_returns[-5:]) - 1
    )
    assert report.volatility_window_count == 61
    assert 0 < report.recent_volatility_percentile <= 1
    assert report.public_display_allowed is False
    assert report.is_prediction is False


def test_aggregate_is_only_buy_and_hold_total_period_change() -> None:
    first = analyze_asset_history("SPY", history([0.01] * 60), trailing_window=60)
    second = analyze_asset_history("TLT", history([-0.005] * 60), trailing_window=60)
    result = weighted_total_change(first, second, first_weight=0.6)

    assert result.total_return == pytest.approx(
        0.6 * first.period_return + 0.4 * second.period_return
    )
    assert result.basis == "initial_weights_buy_and_hold"
    assert not hasattr(result, "correlation")
    with pytest.raises(ValueError, match="same start and end"):
        weighted_total_change(
            first, analyze_asset_history("TLT", history([-0.005] * 60, offset=1)),
            first_weight=0.6,
        )


def test_insufficient_single_asset_history_blocks_summary() -> None:
    with pytest.raises(ValueError, match="insufficient price observations"):
        analyze_asset_history("SPY", history([0.01] * 7))

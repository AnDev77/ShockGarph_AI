from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from shockgraph_domain.portfolio import validate_positions
from shockgraph_domain.records import AssetPriceRecord
from shockgraph_risk.rebalance import Policy, simulate_rebalance


def panel():
    sessions = (date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7))
    times = {day: datetime(day.year, day.month, day.day, 22, tzinfo=UTC) for day in sessions}
    prices = {"SPY": (100, 200, 100), "TLT": (100, 100, 100)}
    rows = {}
    for symbol, values in prices.items():
        rows[symbol] = tuple(
            AssetPriceRecord(
                source="synthetic-fixture", symbol=symbol, venue="XNAS",
                observed_at=times[day] - timedelta(hours=1),
                available_at=times[day] - timedelta(minutes=30),
                session_date=day, currency="USD", close=Decimal(value),
                adjusted_close=Decimal(value),
                raw_payload_hash=hashlib.sha256(f"{symbol}:{day}".encode()).hexdigest(),
            )
            for day, value in zip(sessions, values, strict=True)
        )
    return rows, sessions, times


def run(
    policy: Policy = "hold", *,
    review_sessions: tuple[date, ...] = (), threshold: float = 0.05,
    cost_rate: float = 0.0, contributions: dict[date, float] | None = None,
    withdrawals: dict[date, float] | None = None,
):
    rows, sessions, times = panel()
    portfolio = validate_positions([
        {"symbol": "SPY", "weight": 0.5}, {"symbol": "TLT", "weight": 0.5}
    ])
    return simulate_rebalance(
        rows, sessions, times, portfolio, policy=policy,
        review_sessions=review_sessions, threshold=threshold,
        cost_rate=cost_rate, contributions=contributions, withdrawals=withdrawals,
    )


def test_hold_drifts_and_periodic_trade_affects_only_next_interval() -> None:
    held = run()
    traded = run("periodic", review_sessions=(date(2026, 1, 6),))
    assert held.days[1].value == pytest.approx(1.5)
    assert held.days[1].weights == pytest.approx((2 / 3, 1 / 3))
    assert traded.days[1].value == pytest.approx(held.days[1].value)
    assert traded.days[1].weights == pytest.approx((0.5, 0.5))
    assert held.days[2].value == pytest.approx(1.0)
    assert traded.days[2].value == pytest.approx(1.125)


def test_threshold_and_fee_use_same_close_and_fee_reduces_value() -> None:
    sessions = panel()[1]
    no_trade = run("threshold", review_sessions=(sessions[1],), threshold=0.2)
    trade = run("threshold", review_sessions=(sessions[1],), threshold=0.1, cost_rate=0.01)
    assert not no_trade.days[1].rebalanced
    assert trade.days[1].rebalanced
    assert trade.days[1].cost == pytest.approx(trade.days[1].traded_notional * 0.01)
    assert trade.days[1].value < no_trade.days[1].value
    assert trade.days[1].cash == pytest.approx(0, abs=1e-12)
    assert trade.days[2].value < run("periodic", review_sessions=(sessions[1],)).days[2].value


def test_contribution_waits_as_cash_until_a_review_and_repeat_is_identical() -> None:
    sessions = panel()[1]
    contributions = {sessions[1]: 0.3}
    held = run(contributions=contributions)
    periodic = run("periodic", review_sessions=(sessions[1],), contributions=contributions)
    assert held.days[1].cash == pytest.approx(0.3)
    assert periodic.days[1].cash == pytest.approx(0)
    assert periodic == run("periodic", review_sessions=(sessions[1],), contributions=contributions)


def test_unavailable_price_missing_session_and_bad_inputs_fail_closed() -> None:
    rows, sessions, times = panel()
    portfolio = validate_positions([
        {"symbol": "SPY", "weight": 0.5}, {"symbol": "TLT", "weight": 0.5}
    ])
    late = dict(rows)
    late["SPY"] = rows["SPY"][:1] + (
        rows["SPY"][1].model_copy(
            update={"available_at": times[sessions[1]] + timedelta(seconds=1)}
        ),
    ) + rows["SPY"][2:]
    with pytest.raises(ValueError, match="unavailable"):
        simulate_rebalance(late, sessions, times, portfolio, policy="hold")
    missing = dict(rows)
    missing["TLT"] = rows["TLT"][:2]
    with pytest.raises(ValueError, match="every expected session"):
        simulate_rebalance(missing, sessions, times, portfolio, policy="hold")
    with pytest.raises(ValueError, match="contributions"):
        run(contributions={sessions[1]: -0.1})
    with pytest.raises(ValueError, match="review sessions"):
        run("periodic", review_sessions=(sessions[0],))


def test_future_price_change_does_not_change_earlier_trade_decision() -> None:
    rows, sessions, times = panel()
    portfolio = validate_positions([
        {"symbol": "SPY", "weight": 0.5}, {"symbol": "TLT", "weight": 0.5}
    ])
    kwargs = {"policy": "threshold", "review_sessions": (sessions[1],), "threshold": 0.1}
    original = simulate_rebalance(rows, sessions, times, portfolio, **kwargs)
    changed = dict(rows)
    changed["SPY"] = rows["SPY"][:2] + (
        rows["SPY"][2].model_copy(update={"adjusted_close": Decimal(1000)}),
    )
    revised = simulate_rebalance(changed, sessions, times, portfolio, **kwargs)
    assert revised.days[:2] == original.days[:2]
    assert revised.days[2] != original.days[2]


def test_withdrawal_uses_new_and_existing_cash_before_any_sale() -> None:
    session = panel()[1][1]
    result = run(contributions={session: 0.3}, withdrawals={session: 0.2})
    day = result.days[1]
    assert day.value == pytest.approx(1.6)
    assert day.cash == pytest.approx(0.1)
    assert day.withdrawal == pytest.approx(0.2)
    assert day.forced_sale_notional == 0
    assert day.traded_notional == 0


def test_forced_sale_funds_shortfall_and_charges_fee() -> None:
    session = panel()[1][1]
    result = run(withdrawals={session: 0.4}, cost_rate=0.01)
    day = result.days[1]
    assert not day.rebalanced
    assert day.forced_sale_notional == pytest.approx(0.4 / 0.99)
    assert day.traded_notional == pytest.approx(day.forced_sale_notional)
    assert day.cost == pytest.approx(day.forced_sale_notional * 0.01)
    assert day.value == pytest.approx(1.5 - 0.4 - day.cost)
    assert day.cash == pytest.approx(0)
    assert day.weights == pytest.approx((2 / 3, 1 / 3))


def test_forced_sale_and_review_trade_have_separate_accounting() -> None:
    session = panel()[1][1]
    result = run("periodic", review_sessions=(session,), withdrawals={session: 0.4},
                 cost_rate=0.01)
    day = result.days[1]
    assert day.rebalanced
    assert day.weights == pytest.approx((0.5, 0.5))
    assert day.traded_notional > day.forced_sale_notional
    assert day.cost == pytest.approx(day.traded_notional * 0.01)
    assert day.value == pytest.approx(1.5 - day.withdrawal - day.cost)


def test_invalid_or_unfunded_withdrawals_fail_closed() -> None:
    session = panel()[1][1]
    for amount in (-0.1, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="withdrawals"):
            run(withdrawals={session: amount})
    with pytest.raises(ValueError, match="withdrawal dates"):
        run(withdrawals={date(2026, 1, 8): 0.1})
    with pytest.raises(ValueError, match="withdrawal exceeds"):
        run(withdrawals={session: 1.5})
    with pytest.raises(ValueError, match="withdrawal exceeds"):
        run(withdrawals={session: 1.495}, cost_rate=0.01)


def test_future_withdrawal_does_not_change_past_policy_result() -> None:
    session = panel()[1][2]
    assert run(withdrawals={session: 0.1}).days[:2] == run().days[:2]

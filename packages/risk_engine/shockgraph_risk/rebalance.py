"""Deterministic, close-to-close portfolio policy baselines (no trade execution)."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from shockgraph_domain.portfolio import PortfolioValidationResult
from shockgraph_domain.records import AssetPriceRecord

from shockgraph_risk.portfolio import _panel, _price, _utc

Policy = Literal["hold", "periodic", "threshold"]


@dataclass(frozen=True, slots=True)
class RebalanceDay:
    session_date: date
    value: float
    weights: tuple[float, ...]
    cash: float
    traded_notional: float
    cost: float
    rebalanced: bool


@dataclass(frozen=True, slots=True)
class RebalanceResult:
    policy: Policy
    symbols: tuple[str, ...]
    days: tuple[RebalanceDay, ...]


def simulate_rebalance(
    prices_by_symbol: Mapping[str, Sequence[AssetPriceRecord]],
    expected_sessions: Sequence[date],
    decision_times: Mapping[date, datetime],
    portfolio: PortfolioValidationResult,
    *,
    policy: Policy,
    review_sessions: Sequence[date] = (),
    threshold: float = 0.05,
    cost_rate: float = 0.0,
    initial_value: float = 1.0,
    contributions: Mapping[date, float] | None = None,
) -> RebalanceResult:
    """Value holdings at each close, then decide trades for the *next* return interval.

    Prices must be aligned USD adjusted closes available by the decision time.
    Contributions enter cash at that close; only a scheduled rebalance invests them.
    Withdrawals, tax, spreads, and fractional-share restrictions are not modeled.
    """
    if policy not in ("hold", "periodic", "threshold"):
        raise ValueError("unknown policy")
    if not math.isfinite(initial_value) or initial_value <= 0:
        raise ValueError("initial_value must be finite and positive")
    if not math.isfinite(cost_rate) or not 0 <= cost_rate < 1:
        raise ValueError("cost_rate must be in [0, 1)")
    if not math.isfinite(threshold) or not 0 < threshold < 1:
        raise ValueError("threshold must be in (0, 1)")
    positions, ordered = _panel(prices_by_symbol, expected_sessions, portfolio)
    sessions = tuple(expected_sessions)
    if set(decision_times) != set(sessions):
        raise ValueError("one decision time is required per session")
    times = tuple(_utc(decision_times[session], "decision_at") for session in sessions)
    if any(b <= a for a, b in zip(times, times[1:], strict=False)):
        raise ValueError("decision times must strictly increase")
    reviews = tuple(review_sessions)
    if len(set(reviews)) != len(reviews) or not set(reviews) <= set(sessions[1:]):
        raise ValueError("review sessions must be unique and after the initial session")
    flows = contributions or {}
    if not set(flows) <= set(sessions):
        raise ValueError("contribution dates must belong to the panel")
    if any(not math.isfinite(amount) or amount < 0 for amount in flows.values()):
        raise ValueError("contributions must be finite and non-negative")

    symbols = tuple(position.symbol for position in positions)
    targets = tuple(position.weight for position in positions)
    holdings = [initial_value * weight for weight in targets]
    cash = 0.0
    days: list[RebalanceDay] = []
    for index, session in enumerate(sessions):
        if index:
            for asset, symbol in enumerate(symbols):
                holdings[asset] *= _price(ordered[symbol][index]) / _price(
                    ordered[symbol][index - 1]
                )
        for symbol in symbols:
            row = ordered[symbol][index]
            if row.available_at is None or row.available_at > times[index]:
                raise ValueError("a price is unavailable at decision_at")
        cash += flows.get(session, 0.0)
        total = math.fsum(holdings) + cash
        if not math.isfinite(total) or total <= 0:
            raise ValueError("portfolio value must stay finite and positive")
        current_weights = tuple(value / total for value in holdings)
        should_trade = index > 0 and session in reviews and (
            policy == "periodic"
            or (policy == "threshold" and max(
                abs(actual - target) for actual, target in zip(
                    current_weights, targets, strict=True
                )
            ) > threshold)
        )
        turnover = 0.0
        cost = 0.0
        if should_trade:
            old_holdings = tuple(holdings)
            # Solve the fee/target-value fixed point. A fee changes the amount
            # available to buy; charging it after setting target weights would
            # silently leave a negative cash balance.
            for _ in range(100):
                turnover = math.fsum(
                    abs(target * (total - cost) - held)
                    for target, held in zip(targets, holdings, strict=True)
                )
                updated = turnover * cost_rate
                if math.isclose(updated, cost, rel_tol=1e-13, abs_tol=1e-14):
                    cost = updated
                    break
                cost = updated
            else:
                raise ValueError("transaction cost did not converge")
            net = total - cost
            if net <= 0:
                raise ValueError("transaction cost exhausts the portfolio")
            holdings = [target * net for target in targets]
            cash = net - math.fsum(holdings)
            total = net
            turnover = math.fsum(
                abs(new - old) for new, old in zip(holdings, old_holdings, strict=True)
            )
        days.append(RebalanceDay(
            session_date=session,
            value=total,
            weights=tuple(value / total for value in holdings),
            cash=cash,
            traded_notional=turnover,
            cost=cost,
            rebalanced=should_trade,
        ))
    return RebalanceResult(policy=policy, symbols=symbols, days=tuple(days))

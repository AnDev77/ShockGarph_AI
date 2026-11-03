from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from shockgraph_domain.portfolio import validate_positions
from shockgraph_domain.records import AssetPriceRecord
from shockgraph_risk.point_in_time_panel import select_point_in_time_panel
from shockgraph_risk.rebalance import simulate_rebalance


def _row(symbol: str, session: date, available: datetime, price: int) -> AssetPriceRecord:
    return AssetPriceRecord(
        source="synthetic-research", symbol=symbol, venue="XNAS",
        observed_at=available - timedelta(minutes=30), available_at=available,
        session_date=session, currency="USD", close=Decimal(price),
        adjusted_close=Decimal(price),
        raw_payload_hash=hashlib.sha256(f"{symbol}:{session}:{available}:{price}".encode()).hexdigest(),
    )


def _input():
    sessions = (date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7))
    decisions = {day: datetime(day.year, day.month, day.day, 22, tzinfo=UTC) for day in sessions}
    versions = {
        symbol: tuple(_row(symbol, day, decisions[day] - timedelta(minutes=10), value)
                      for day, value in zip(sessions, values, strict=True))
        for symbol, values in {"SPY": (100, 120, 110), "QQQ": (100, 100, 100)}.items()
    }
    sources = {symbol: "synthetic-research" for symbol in versions}
    return sessions, decisions, versions, sources


def test_later_revision_never_changes_earlier_policy_decision() -> None:
    sessions, decisions, versions, sources = _input()
    base = select_point_in_time_panel(versions, sessions, decisions, research_sources=sources)
    revised = dict(versions)
    revised["SPY"] += (_row("SPY", sessions[1], decisions[sessions[2]] + timedelta(hours=1), 500),)
    panel = select_point_in_time_panel(revised, sessions, decisions, research_sources=sources)
    assert panel.prices_by_symbol == base.prices_by_symbol
    portfolio = validate_positions([{"symbol": "SPY", "weight": 0.5},
                                    {"symbol": "QQQ", "weight": 0.5}])
    result = simulate_rebalance(panel.prices_by_symbol, panel.sessions, panel.decision_times,
                                portfolio, policy="threshold", review_sessions=(sessions[1],),
                                threshold=0.01)
    assert result.days[1].rebalanced


def test_latest_eligible_version_is_selected_and_provenance_preserved() -> None:
    sessions, decisions, versions, sources = _input()
    revised = dict(versions)
    chosen = _row("SPY", sessions[1], decisions[sessions[1]] - timedelta(minutes=1), 121)
    revised["SPY"] += (chosen,)
    panel = select_point_in_time_panel(revised, sessions, decisions, research_sources=sources)
    assert panel.prices_by_symbol["SPY"][1].raw_payload_hash == chosen.raw_payload_hash


@pytest.mark.parametrize("change,match", [
    ("missing", "missing or unavailable"),
    ("late", "missing or unavailable"),
    ("ambiguous", "ambiguous"),
    ("source", "source differs"),
    ("currency", "USD adjusted"),
])
def test_bad_panel_fails_closed(change: str, match: str) -> None:
    sessions, decisions, versions, sources = _input()
    changed = dict(versions)
    rows = list(changed["SPY"])
    if change == "missing":
        rows.pop(1)
    elif change == "late":
        rows[1] = _row("SPY", sessions[1], decisions[sessions[1]] + timedelta(minutes=1), 120)
    elif change == "ambiguous":
        rows.append(rows[1].model_copy(update={"raw_payload_hash": "a" * 64}))
    elif change == "source":
        rows[1] = rows[1].model_copy(update={"source": "other"})
    else:
        rows[1] = rows[1].model_copy(update={"currency": "KRW"})
    changed["SPY"] = tuple(rows)
    with pytest.raises(ValueError, match=match):
        select_point_in_time_panel(changed, sessions, decisions, research_sources=sources)

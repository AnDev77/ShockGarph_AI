"""Select immutable daily price versions usable at each historical decision cutoff.

This is a research input gate. A source allowlist is not a display or resale licence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from shockgraph_domain.records import AssetPriceRecord

from shockgraph_risk.portfolio import _utc


@dataclass(frozen=True, slots=True)
class PointInTimePanel:
    sessions: tuple[date, ...]
    decision_times: Mapping[date, datetime]
    prices_by_symbol: Mapping[str, tuple[AssetPriceRecord, ...]]


def select_point_in_time_panel(
    versions_by_symbol: Mapping[str, Sequence[AssetPriceRecord]],
    expected_sessions: Sequence[date],
    decision_times: Mapping[date, datetime],
    *,
    research_sources: Mapping[str, str],
) -> PointInTimePanel:
    """Choose the latest version *already available* at each session's decision time.

    Missing sessions, ambiguous vintages, wrong sources, or late-only prices fail closed.
    The caller must separately verify source permissions and corporate-action policy.
    """
    sessions = tuple(expected_sessions)
    if not sessions or tuple(sorted(set(sessions))) != sessions:
        raise ValueError("expected_sessions must be nonempty, unique, and increasing")
    symbols = set(versions_by_symbol)
    if not symbols or set(research_sources) != symbols:
        raise ValueError("research_sources must match price symbols exactly")
    if set(decision_times) != set(sessions):
        raise ValueError("one decision time is required for every session")
    times = {session: _utc(decision_times[session], "decision_at") for session in sessions}
    ordered_times = tuple(times.values())
    if any(b <= a for a, b in zip(ordered_times, ordered_times[1:], strict=False)):
        raise ValueError("decision times must increase with sessions")

    selected: dict[str, tuple[AssetPriceRecord, ...]] = {}
    for symbol, versions in versions_by_symbol.items():
        if not research_sources[symbol]:
            raise ValueError("research source must be named")
        grouped: dict[date, list[AssetPriceRecord]] = {session: [] for session in sessions}
        for row in versions:
            if row.symbol != symbol or row.source != research_sources[symbol]:
                raise ValueError("price symbol or source differs from the research contract")
            if row.session_date not in grouped:
                raise ValueError("price version has an unexpected session")
            if row.currency != "USD" or row.adjusted_close is None or row.available_at is None:
                raise ValueError("USD adjusted close and exact available_at are required")
            grouped[row.session_date].append(row)
        chosen: list[AssetPriceRecord] = []
        for session in sessions:
            eligible = [
                row for row in grouped[session]
                if row.available_at is not None and row.available_at <= times[session]
            ]
            if not eligible:
                raise ValueError("a price is missing or unavailable at decision_at")
            latest_at = max(row.available_at for row in eligible if row.available_at is not None)
            newest = [row for row in eligible if row.available_at == latest_at]
            if len(newest) != 1:
                raise ValueError("ambiguous price versions at the same available_at")
            chosen.append(newest[0])
        venues = {row.venue for row in chosen}
        if len(venues) != 1:
            raise ValueError("price venue changed across the panel")
        selected[symbol] = tuple(chosen)
    return PointInTimePanel(sessions, times, selected)

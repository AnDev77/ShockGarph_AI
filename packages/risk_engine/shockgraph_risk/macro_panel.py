"""Point-in-time price and traditional inputs, with an optional probability research join.

This joins already captured records. It does not train, score, or license a model.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from shockgraph_analytics.contracts import ProbabilitySnapshot

from shockgraph_risk.daily import VolatilityForecast, _utc

_HASH = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class MarketIndicatorObservation:
    name: str
    source: str
    observed_at: datetime
    available_at: datetime
    value: float
    raw_hash: str

    def __post_init__(self) -> None:
        _utc(self.observed_at, "indicator observed_at")
        _utc(self.available_at, "indicator available_at")
        if self.available_at < self.observed_at:
            raise ValueError("indicator cannot be available before observation")
        if not self.name or not self.source or not _HASH.fullmatch(self.raw_hash):
            raise ValueError("indicator needs a name, source, and raw SHA-256")
        if not math.isfinite(self.value):
            raise ValueError("indicator value must be finite")


@dataclass(frozen=True, slots=True)
class ScheduledMacroEvent:
    event_id: str
    category: str
    source: str
    market_ticker: str
    announced_at: datetime
    available_at: datetime
    release_at: datetime
    raw_hash: str

    def __post_init__(self) -> None:
        _utc(self.announced_at, "event announced_at")
        _utc(self.available_at, "event available_at")
        _utc(self.release_at, "event release_at")
        if not self.announced_at <= self.available_at < self.release_at:
            raise ValueError("event schedule must be usable before its release")
        if (not self.event_id or not self.category or not self.source
                or not self.market_ticker or not _HASH.fullmatch(self.raw_hash)):
            raise ValueError("event needs an id, category, source, contract, and raw SHA-256")


@dataclass(frozen=True, slots=True)
class TraditionalFeatureRow:
    forecast: VolatilityForecast
    indicators: tuple[MarketIndicatorObservation, ...]


@dataclass(frozen=True, slots=True)
class ProbabilityFeatureRow:
    traditional: TraditionalFeatureRow
    event: ScheduledMacroEvent
    probability: ProbabilitySnapshot


@dataclass(frozen=True, slots=True)
class PanelCoverage:
    baseline_count: int
    traditional_count: int
    probability_count: int
    unique_probability_events: int
    exclusions: tuple[tuple[str, int], ...]
    indicator_exclusions: tuple[tuple[str, str, int], ...] = ()


@dataclass(frozen=True, slots=True)
class MacroRiskPanel:
    baseline_rows: tuple[VolatilityForecast, ...]
    traditional_rows: tuple[TraditionalFeatureRow, ...]
    probability_rows: tuple[ProbabilityFeatureRow, ...]
    coverage: PanelCoverage


def build_macro_risk_panel(
    forecasts: Sequence[VolatilityForecast],
    indicators: Sequence[MarketIndicatorObservation],
    events: Sequence[ScheduledMacroEvent],
    probabilities: Sequence[ProbabilitySnapshot],
    *,
    required_indicators: tuple[str, ...],
    max_indicator_age: timedelta,
    indicator_max_ages: Mapping[str, timedelta] | None = None,
    max_probability_age: timedelta,
    max_release_lead: timedelta,
    include_probability_research: bool = True,
) -> MacroRiskPanel:
    """Create B rows and optionally a strictly matched A/B/C research sample.

    Age/lead settings and the contract for each release must be fixed before evaluation.
    Missing observations remain excluded; a missing probability never becomes zero.
    """
    if not required_indicators or any(not name for name in required_indicators):
        raise ValueError("required_indicators must be nonempty names")
    if len(set(required_indicators)) != len(required_indicators):
        raise ValueError("required_indicators must be unique")
    configured_ages = dict(indicator_max_ages or {})
    if set(configured_ages) - set(required_indicators):
        raise ValueError("unknown indicator age override")
    if any(not isinstance(age, timedelta) or age <= timedelta(0)
           for age in configured_ages.values()):
        raise ValueError("positive indicator age required")
    if any(age <= timedelta(0) for age in (
        max_indicator_age, max_probability_age, max_release_lead
    )):
        raise ValueError("age and release lead limits must be positive")
    if not include_probability_research and (events or probabilities):
        raise ValueError("probability research inputs must be empty when disabled")

    baseline = tuple(forecasts)
    if baseline:
        first = baseline[0]
        previous_at: datetime | None = None
        previous_date = None
        seen_sessions = set()
        for forecast in baseline:
            _utc(forecast.prediction_at, "prediction_at")
            if (forecast.symbol, forecast.horizon) != (first.symbol, first.horizon):
                raise ValueError("forecasts must share one asset and horizon")
            if forecast.session_date in seen_sessions or (
                previous_at is not None and forecast.prediction_at <= previous_at
            ) or (
                previous_date is not None and forecast.session_date <= previous_date
            ):
                raise ValueError("forecasts must have unique, increasing sessions and times")
            if not forecast.input_fingerprint or not _HASH.fullmatch(forecast.input_fingerprint):
                raise ValueError("archived price input fingerprint is required")
            if any(not math.isfinite(value) or value < 0 for value in (
                forecast.trailing_volatility, forecast.ewma_volatility
            )):
                raise ValueError("baseline volatility must be finite and nonnegative")
            seen_sessions.add(forecast.session_date)
            previous_at = forecast.prediction_at
            previous_date = forecast.session_date

    by_indicator: dict[str, list[MarketIndicatorObservation]] = defaultdict(list)
    series_sources: dict[str, str] = {}
    indicator_keys = set()
    for row in indicators:
        key = (row.name, row.observed_at, row.available_at)
        if key in indicator_keys:
            raise ValueError("duplicate indicator vintage")
        indicator_keys.add(key)
        if row.name in series_sources and series_sources[row.name] != row.source:
            raise ValueError("one indicator series cannot mix sources")
        series_sources[row.name] = row.source
        by_indicator[row.name].append(row)

    event_ids = set()
    for event in events:
        if event.event_id in event_ids:
            raise ValueError("one fixed schedule and contract per event are required")
        event_ids.add(event.event_id)

    by_probability: dict[tuple[str, str], list[ProbabilitySnapshot]] = defaultdict(list)
    snapshot_keys = set()
    for row in probabilities:
        _utc(row.observed_at, "probability observed_at")
        _utc(row.available_at, "probability available_at")
        if row.available_at < row.observed_at or not math.isfinite(row.probability) or not (
            0 <= row.probability <= 1
        ):
            raise ValueError("invalid probability snapshot")
        key = (row.event_id, row.market_ticker, row.observed_at, row.available_at)
        if key in snapshot_keys:
            raise ValueError("duplicate probability vintage")
        snapshot_keys.add(key)
        by_probability[(row.event_id, row.market_ticker)].append(row)

    traditional: list[TraditionalFeatureRow] = []
    joined: list[ProbabilityFeatureRow] = []
    excluded: Counter[str] = Counter()
    indicator_excluded: Counter[tuple[str, str]] = Counter()
    for forecast in baseline:
        at = forecast.prediction_at
        selected_indicators = []
        for name in required_indicators:
            eligible = [
                row for row in by_indicator[name]
                if row.observed_at <= at and row.available_at <= at
            ]
            if not eligible:
                excluded["missing_indicator"] += 1
                indicator_excluded[(name, "missing_indicator")] += 1
                break
            latest = max(eligible, key=lambda row: (row.observed_at, row.available_at))
            if at - latest.observed_at > configured_ages.get(name, max_indicator_age):
                excluded["stale_indicator"] += 1
                indicator_excluded[(name, "stale_indicator")] += 1
                break
            selected_indicators.append(latest)
        else:
            b_row = TraditionalFeatureRow(forecast, tuple(selected_indicators))
            traditional.append(b_row)
            if not include_probability_research:
                continue
            known_events = [
                event for event in events
                if event.available_at <= at < event.release_at
                and event.release_at - at <= max_release_lead
            ]
            if not known_events:
                excluded["no_known_upcoming_event"] += 1
                continue
            event = min(known_events, key=lambda row: (row.release_at, row.event_id))
            snapshots = [
                row for row in by_probability[(event.event_id, event.market_ticker)]
                if row.observed_at <= at and row.available_at <= at
                and row.observed_at < event.release_at
                and row.available_at < event.release_at
            ]
            if not snapshots:
                excluded["missing_probability"] += 1
                continue
            snapshot = max(snapshots, key=lambda row: (row.observed_at, row.available_at))
            if at - snapshot.observed_at > max_probability_age:
                excluded["stale_probability"] += 1
                continue
            joined.append(ProbabilityFeatureRow(b_row, event, snapshot))

    coverage = PanelCoverage(
        baseline_count=len(baseline),
        traditional_count=len(traditional),
        probability_count=len(joined),
        unique_probability_events=len({row.event.event_id for row in joined}),
        exclusions=tuple(sorted(excluded.items())),
        indicator_exclusions=tuple(
            (name, reason, count) for (name, reason), count in sorted(indicator_excluded.items())
        ),
    )
    return MacroRiskPanel(baseline, tuple(traditional), tuple(joined), coverage)

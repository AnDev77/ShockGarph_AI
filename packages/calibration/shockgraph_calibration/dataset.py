from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True, slots=True)
class CalibrationObservation:
    event_id: str
    probability: float
    outcome: Literal[0, 1]
    observed_at: datetime
    feature_as_of: datetime
    resolved_at: datetime

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id is required")
        if not 0 <= self.probability <= 1:
            raise ValueError("probability must be in [0, 1]")
        for name in ("observed_at", "feature_as_of", "resolved_at"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware UTC")
            if value.utcoffset() != UTC.utcoffset(value):
                raise ValueError(f"{name} must be stored in UTC")
        if self.feature_as_of > self.observed_at:
            raise ValueError("feature_as_of cannot follow observed_at")
        if self.observed_at >= self.resolved_at:
            raise ValueError("observed_at must precede resolved_at")


@dataclass(frozen=True, slots=True)
class CalibrationSplits:
    train: tuple[CalibrationObservation, ...]
    validation: tuple[CalibrationObservation, ...]
    test: tuple[CalibrationObservation, ...]


def build_calibration_dataset(
    observations: Sequence[Mapping[str, object]],
) -> tuple[CalibrationObservation, ...]:
    rows: list[CalibrationObservation] = []
    outcomes_by_event: dict[str, int] = {}
    resolutions_by_event: dict[str, datetime] = {}
    for raw in observations:
        event_id = raw.get("event_id")
        outcome = raw.get("outcome")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("event_id is required")
        if outcome not in (0, 1):
            raise ValueError("outcome must be binary")
        prior = outcomes_by_event.setdefault(event_id, outcome)
        if prior != outcome:
            raise ValueError(f"conflicting outcomes for event_id {event_id!r}")
        resolved_at = _datetime(raw, "resolved_at")
        prior_resolution = resolutions_by_event.setdefault(event_id, resolved_at)
        if prior_resolution != resolved_at:
            raise ValueError(f"conflicting resolution timestamps for event_id {event_id!r}")
        rows.append(
            CalibrationObservation(
                event_id=event_id,
                probability=_probability(raw),
                outcome=outcome,
                observed_at=_datetime(raw, "observed_at"),
                feature_as_of=_datetime(raw, "feature_as_of"),
                resolved_at=resolved_at,
            )
        )
    return tuple(sorted(rows, key=lambda row: (row.resolved_at, row.event_id, row.observed_at)))


def chronological_event_split(
    rows: Sequence[CalibrationObservation],
    *,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
) -> CalibrationSplits:
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1:
        raise ValueError("split fractions must be in (0, 1)")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train and validation fractions must leave a test split")

    ordered_events = sorted(
        {row.event_id: row.resolved_at for row in rows}.items(), key=lambda item: (item[1], item[0])
    )
    event_count = len(ordered_events)
    if event_count < 3:
        raise ValueError("at least three independent events are required")

    train_end = max(1, int(event_count * train_fraction))
    validation_end = max(train_end + 1, int(event_count * (train_fraction + validation_fraction)))
    validation_end = min(validation_end, event_count - 1)
    train_ids = {event_id for event_id, _ in ordered_events[:train_end]}
    validation_ids = {event_id for event_id, _ in ordered_events[train_end:validation_end]}
    test_ids = {event_id for event_id, _ in ordered_events[validation_end:]}

    return CalibrationSplits(
        train=tuple(row for row in rows if row.event_id in train_ids),
        validation=tuple(row for row in rows if row.event_id in validation_ids),
        test=tuple(row for row in rows if row.event_id in test_ids),
    )


def _datetime(row: Mapping[str, object], field: str) -> datetime:
    value = row.get(field)
    if not isinstance(value, datetime):
        raise ValueError(f"{field} must be a datetime")
    return value


def _probability(row: Mapping[str, object]) -> float:
    value = row.get("probability")
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("probability must be numeric")
    return float(value)

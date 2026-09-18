from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any


class LeakageViolation(ValueError):
    """Raised when dataset construction would leak future information."""


def _utc_datetime(row: Mapping[str, Any], field: str) -> datetime:
    value = row.get(field)
    if not isinstance(value, datetime):
        raise LeakageViolation(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise LeakageViolation(f"{field} must be timezone-aware")
    if value.astimezone(UTC).utcoffset() != value.utcoffset():
        raise LeakageViolation(f"{field} must be stored in UTC")
    return value


def validate_dataset_splits(splits: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    event_owners: dict[str, str] = {}

    for split_name, rows in splits.items():
        for row in rows:
            event_id = row.get("event_id")
            if not isinstance(event_id, str) or not event_id:
                raise LeakageViolation("event_id is required")

            owner = event_owners.setdefault(event_id, split_name)
            if owner != split_name:
                raise LeakageViolation(
                    f"event_id {event_id!r} appears in both {owner!r} and {split_name!r}"
                )

            observed_at = _utc_datetime(row, "observed_at")
            resolved_at = _utc_datetime(row, "resolved_at")
            feature_as_of = _utc_datetime(row, "feature_as_of")

            if observed_at >= resolved_at:
                raise LeakageViolation(f"event_id {event_id!r} observed on or after resolution")
            if feature_as_of > observed_at:
                raise LeakageViolation(f"event_id {event_id!r} uses future information")


from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from shockgraph_data_pipeline.leakage import LeakageViolation, validate_dataset_splits


def row(event_id: str, observed_at: datetime, resolved_at: datetime) -> dict:
    return {
        "event_id": event_id,
        "observed_at": observed_at,
        "feature_as_of": observed_at,
        "resolved_at": resolved_at,
    }


def test_same_event_cannot_cross_splits() -> None:
    resolved = datetime(2026, 8, 12, 12, 35, tzinfo=UTC)
    splits = {
        "train": [row("cpi-aug", resolved - timedelta(days=2), resolved)],
        "test": [row("cpi-aug", resolved - timedelta(days=1), resolved)],
    }

    with pytest.raises(LeakageViolation, match="appears in both"):
        validate_dataset_splits(splits)


def test_post_resolution_observation_is_rejected() -> None:
    resolved = datetime(2026, 8, 12, 12, 35, tzinfo=UTC)
    splits = {"train": [row("cpi-aug", resolved, resolved)]}

    with pytest.raises(LeakageViolation, match="on or after resolution"):
        validate_dataset_splits(splits)


def test_future_feature_timestamp_is_rejected() -> None:
    resolved = datetime(2026, 8, 12, 12, 35, tzinfo=UTC)
    item = row("cpi-aug", resolved - timedelta(hours=2), resolved)
    item["feature_as_of"] = item["observed_at"] + timedelta(minutes=1)

    with pytest.raises(LeakageViolation, match="future information"):
        validate_dataset_splits({"train": [item]})


def test_valid_grouped_chronological_rows_pass() -> None:
    resolved = datetime(2026, 8, 12, 12, 35, tzinfo=UTC)
    splits = {
        "train": [row("cpi-jul", resolved - timedelta(days=30), resolved - timedelta(days=20))],
        "validation": [row("cpi-aug", resolved - timedelta(days=1), resolved)],
    }

    validate_dataset_splits(splits)


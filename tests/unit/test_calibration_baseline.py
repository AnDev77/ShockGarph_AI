from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from shockgraph_calibration.dataset import (
    build_calibration_dataset,
    chronological_event_split,
)
from shockgraph_calibration.metrics import brier_score, identity_predictions


def raw_row(event_id: str, day: int, probability: float, outcome: int) -> dict:
    resolved = datetime(2026, 1, day, 14, tzinfo=UTC)
    observed = resolved - timedelta(days=1)
    return {
        "event_id": event_id,
        "probability": probability,
        "outcome": outcome,
        "observed_at": observed,
        "feature_as_of": observed,
        "resolved_at": resolved,
    }


def test_chronological_split_keeps_all_rows_of_event_together() -> None:
    rows = build_calibration_dataset(
        [
            raw_row("event-1", 1, 0.2, 0),
            raw_row("event-1", 1, 0.3, 0),
            raw_row("event-2", 2, 0.4, 0),
            raw_row("event-3", 3, 0.6, 1),
            raw_row("event-4", 4, 0.8, 1),
            raw_row("event-5", 5, 0.9, 1),
        ]
    )

    splits = chronological_event_split(rows)
    split_ids = [
        {row.event_id for row in splits.train},
        {row.event_id for row in splits.validation},
        {row.event_id for row in splits.test},
    ]

    assert not split_ids[0] & split_ids[1]
    assert not split_ids[0] & split_ids[2]
    assert not split_ids[1] & split_ids[2]
    assert {row.event_id for row in splits.train} == {"event-1", "event-2", "event-3"}


def test_dataset_rejects_post_resolution_observation() -> None:
    row = raw_row("event-1", 1, 0.2, 0)
    row["observed_at"] = row["resolved_at"]

    with pytest.raises(ValueError, match="precede resolved_at"):
        build_calibration_dataset([row])


def test_identity_baseline_reports_brier_sample_size_and_uncertainty() -> None:
    rows = build_calibration_dataset(
        [raw_row("event-1", 1, 0.2, 0), raw_row("event-2", 2, 0.8, 1)]
    )

    report = brier_score(identity_predictions(rows), [row.outcome for row in rows])

    assert report.score == pytest.approx(0.04)
    assert report.sample_size == 2
    assert 0 <= report.confidence_lower <= report.score <= report.confidence_upper <= 1

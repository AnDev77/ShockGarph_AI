from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Any

from shockgraph_analytics.paper_panel import ASSETS

HORIZONS = ("m5", "m30")
KEYS = {(asset, horizon) for asset in ASSETS for horizon in HORIZONS}


def evaluate_price_baseline(
    rows: list[dict[str, Any]], *, min_train: int = 5, min_test: int = 10
) -> dict[str, Any]:
    """Walk forward using the mean return of earlier complete CPI events only."""
    if min_train < 1 or min_test < 1:
        raise ValueError("minimum train and test counts must be positive")
    events: dict[str, dict[tuple[str, str], float]] = defaultdict(dict)
    release_times: dict[str, datetime] = {}
    for row in rows:
        event_id = row["event_id"]
        release_at = row["release_at"]
        key = row["asset_id"], row["horizon"]
        value = float(row["return_value"])
        if key not in KEYS or not math.isfinite(value):
            raise ValueError("unsupported asset/horizon or nonfinite return")
        if not isinstance(release_at, datetime) or release_at.tzinfo is None:
            raise ValueError("release time must be timezone-aware")
        if event_id in release_times and release_times[event_id] != release_at:
            raise ValueError("one event must have one release time")
        if key in events[event_id]:
            raise ValueError("each event requires six unique asset/horizon rows")
        release_times[event_id] = release_at
        events[event_id][key] = value
    if any(set(event_rows) != KEYS for event_rows in events.values()):
        raise ValueError("each event requires six unique asset/horizon rows")
    ordered_ids = sorted(events, key=lambda event_id: (release_times[event_id], event_id))
    if len({release_times[event_id] for event_id in ordered_ids}) != len(ordered_ids):
        raise ValueError("event release times must be distinct")
    predictions: list[dict[str, Any]] = []
    groups: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for index in range(min_train, len(ordered_ids)):
        event_id = ordered_ids[index]
        for asset, horizon in sorted(KEYS):
            prior = [events[prior_id][asset, horizon] for prior_id in ordered_ids[:index]]
            predicted = math.fsum(prior) / len(prior)
            actual = events[event_id][asset, horizon]
            group = f"{asset}:{horizon}"
            predictions.append(
                {
                    "event_id": event_id,
                    "release_at": release_times[event_id].isoformat(),
                    "asset_id": asset,
                    "horizon": horizon,
                    "train_events": index,
                    "predicted_return": predicted,
                    "actual_return": actual,
                }
            )
            groups[group].append((predicted, actual))
    test_events = len(ordered_ids) - min_train
    status = "evaluated" if test_events >= min_test else "insufficient_test_events"
    metrics = (
        {
            group: {
                "test_events": len(values),
                "mae": math.fsum(abs(predicted - actual) for predicted, actual in values)
                / len(values),
                "zero_mae": math.fsum(abs(actual) for _, actual in values) / len(values),
            }
            for group, values in sorted(groups.items())
        }
        if status == "evaluated"
        else {}
    )
    return {
        "status": status,
        "common_events": len(ordered_ids),
        "train_start_events": min_train,
        "test_events": max(0, test_events),
        "required_test_events": min_test,
        "predictions": predictions,
        "metrics": metrics,
    }

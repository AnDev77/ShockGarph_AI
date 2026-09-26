from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from shockgraph_analytics.contracts import Release, ResearchDataset

MODEL_VERSION = "empirical-scenarios-shrinkage-v2"
SHRINKAGE_STRENGTH = 4
MIN_EFFECTIVE_TAIL_OBSERVATIONS = 10


@dataclass(frozen=True)
class PreparedEvent:
    release: Release
    probability: float
    outcome: bool
    returns: tuple[float, ...]
    label_available_at: datetime


def prepare(dataset: ResearchDataset) -> tuple[list[PreparedEvent], list[dict[str, Any]]]:
    prices = {(p.asset_id, p.price_at): p for p in dataset.prices}
    prepared, coverage = [], []
    for release in sorted(dataset.releases, key=lambda r: (r.prediction_at, r.event_id)):
        reason = None
        snapshots = [
            s
            for s in dataset.snapshots
            if s.event_id == release.event_id
            and s.observed_at <= release.prediction_at
            and s.available_at <= release.prediction_at
            and release.prediction_at - s.observed_at
            <= timedelta(hours=dataset.max_snapshot_age_hours)
        ]
        if release.outcome_available_at > dataset.evaluation_at:
            reason = "pending_outcome"
        elif release.expectation_available_at > release.prediction_at:
            reason = "late_expectation"
        elif not snapshots:
            reason = "missing_pre_release_probability"
        values = []
        label_at = release.outcome_available_at
        for asset in dataset.assets:
            start = prices.get((asset, release.return_start_at))
            end = prices.get((asset, release.return_end_at))
            if start is None or end is None:
                reason = reason or f"missing_price:{asset}"
            elif start.available_at > release.prediction_at:
                reason = reason or f"late_start_price:{asset}"
            elif end.available_at > dataset.evaluation_at:
                reason = reason or "pending_outcome"
            else:
                value = end.price / start.price - 1
                if not math.isfinite(value):
                    raise ValueError("non-finite return")
                values.append(value)
                label_at = max(label_at, end.available_at)
        coverage.append(
            {
                "event_id": release.event_id,
                "release_at": release.release_at.isoformat(),
                "status": "excluded" if reason else "ready",
                "reason": reason,
            }
        )
        if reason:
            continue
        chosen = max(snapshots, key=lambda s: s.observed_at)
        prepared.append(
            PreparedEvent(
                release,
                chosen.probability,
                release.actual_value > dataset.threshold,
                tuple(values),
                label_at,
            )
        )
    return prepared, coverage


def empirical_crps(values: list[float], weights: list[float], observed: float) -> float:
    if (
        not values
        or len(values) != len(weights)
        or not all(math.isfinite(v) for v in [*values, *weights, observed])
        or any(w < 0 for w in weights)
        or not math.isclose(sum(weights), 1, abs_tol=1e-9, rel_tol=0)
    ):
        raise ValueError("require finite samples and normalized nonnegative weights")
    first = math.fsum(w * abs(x - observed) for x, w in zip(values, weights, strict=True))
    # Sorted weighted empirical CRPS: O(n log n), avoiding a quadratic sample matrix.
    mass = weighted_sum = pair_half = 0.0
    for value, weight in sorted(zip(values, weights, strict=True)):
        pair_half += weight * (value * mass - weighted_sum)
        mass += weight
        weighted_sum += weight * value
    return max(0.0, first - pair_half)


def quantile(values: list[float], weights: list[float], q: float) -> float:
    total = 0.0
    for value, weight in sorted(zip(values, weights, strict=True)):
        total += weight
        if total >= q - 1e-12:
            return value
    return max(values)


def forecast(values: list[float], weights: list[float]) -> dict[str, float]:
    mean = math.fsum(v * w for v, w in zip(values, weights, strict=True))
    return {
        "mean_return": mean,
        "predictive_std": math.sqrt(
            math.fsum(w * (v - mean) ** 2 for v, w in zip(values, weights, strict=True))
        ),
        "probability_up": math.fsum(w for v, w in zip(values, weights, strict=True) if v > 0),
        "q05": quantile(values, weights, 0.05),
        "q95": quantile(values, weights, 0.95),
    }


def scenario_weights(outcomes: list[bool], probability: float, *, strength: int = 4) -> list[float]:
    """Pool each scenario distribution toward the training-only unconditional distribution."""
    if not outcomes or not 0 <= probability <= 1 or not math.isfinite(probability) or strength < 0:
        raise ValueError("invalid scenario weighting inputs")
    yes = sum(outcomes)
    no = len(outcomes) - yes
    if not yes or not no:
        raise ValueError("both scenarios require observed training events")
    n = len(outcomes)
    return [
        probability
        * (
            (yes / (yes + strength)) * (1 / yes if outcome else 0)
            + (strength / (yes + strength)) / n
        )
        + (1 - probability)
        * (
            (no / (no + strength)) * (1 / no if not outcome else 0)
            + (strength / (no + strength)) / n
        )
        for outcome in outcomes
    ]


def tail_risk(
    values: list[float], weights: list[float], *, alpha: float = 0.05
) -> dict[str, float | str]:
    if (
        not values
        or len(values) != len(weights)
        or not 0 < alpha < 1
        or any(not math.isfinite(x) for x in [*values, *weights])
        or any(w < 0 for w in weights)
        or not math.isclose(math.fsum(weights), 1, abs_tol=1e-9, rel_tol=0)
    ):
        raise ValueError("finite values and normalized nonnegative weights required")
    effective_n = 1 / math.fsum(w * w for w in weights)
    expected_tail = effective_n * alpha
    result: dict[str, float | str] = {
        "status": "insufficient_tail_data",
        "effective_events": effective_n,
        "effective_tail_observations": expected_tail,
    }
    if expected_tail + 1e-9 < MIN_EFFECTIVE_TAIL_OBSERVATIONS:
        return result
    remaining = alpha
    lower_sum = 0.0
    for value, weight in sorted(zip(values, weights, strict=True)):
        take = min(weight, remaining)
        lower_sum += take * value
        remaining -= take
        if remaining <= 1e-12:
            break
    result.update(
        status="exploratory", var95=-quantile(values, weights, alpha), es95=-lower_sum / alpha
    )
    return result


def score(values: list[float], weights: list[float], observed: float) -> dict[str, float]:
    f = forecast(values, weights)
    error = observed - f["q05"]
    return {
        "crps": empirical_crps(values, weights, observed),
        "brier_up": (f["probability_up"] - (observed > 0)) ** 2,
        "pinball05": error * (0.05 - (error < 0)),
        "interval90_covered": float(f["q05"] <= observed <= f["q95"]),
        "interval90_width": f["q95"] - f["q05"],
    }


def paired_interval(differences: list[float], *, seed: int = 42) -> list[float] | None:
    if len(differences) < 2:
        return None
    rng = random.Random(seed)
    means = sorted(
        sum(rng.choices(differences, k=len(differences))) / len(differences) for _ in range(1000)
    )
    return [means[24], means[974]]


def evaluate(
    dataset: ResearchDataset, *, min_train: int = 20, min_scenario: int = 2
) -> dict[str, Any]:
    if min_train < 2 or min_scenario < 2:
        raise ValueError("minimum train and scenario samples must be at least two")
    events, coverage = prepare(dataset)
    folds: list[dict[str, Any]] = []
    names = [*dataset.assets, "portfolio"]
    for current in events:
        train = [
            row
            for row in events
            if row.release.event_id != current.release.event_id
            and row.release.release_at < current.release.prediction_at
            and row.label_available_at <= current.release.prediction_at
            and row.release.return_end_at < current.release.return_start_at
        ]
        yes = sum(row.outcome for row in train)
        no = len(train) - yes
        fold: dict[str, Any] = {
            "event_id": current.release.event_id,
            "prediction_at": current.release.prediction_at.isoformat(),
            "train_event_ids": [row.release.event_id for row in train],
            "scenario_counts": {"yes": yes, "no": no},
        }
        if len(train) < min_train or min(yes, no) < min_scenario:
            fold.update(
                status="skipped",
                reason="insufficient_train_events"
                if len(train) < min_train
                else "insufficient_scenario_samples",
            )
            folds.append(fold)
            continue
        uniform = [1 / len(train)] * len(train)
        conditional = scenario_weights(
            [row.outcome for row in train], current.probability, strength=SHRINKAGE_STRENGTH
        )
        fold.update(status="evaluated", predictions={}, scores={}, tail_risk={})
        for index, name in enumerate(names):

            def value(row: PreparedEvent, asset_index: int = index) -> float:
                if asset_index < len(dataset.assets):
                    return row.returns[asset_index]
                return sum(w * r for w, r in zip(dataset.weights, row.returns, strict=True))

            values = [value(row) for row in train]
            target = value(current)
            fold["predictions"][name] = {
                "historical": forecast(values, uniform),
                "probability_weighted": forecast(values, conditional),
            }
            fold["scores"][name] = {
                "historical": score(values, uniform, target),
                "probability_weighted": score(values, conditional, target),
            }
            fold["tail_risk"][name] = {
                "historical": tail_risk(values, uniform),
                "probability_weighted": tail_risk(values, conditional),
            }
        # Ex post diagnostics never enter forecast construction above.
        fold["diagnostics"] = {
            "realized_surprise": current.release.actual_value - current.release.expected_value,
            "event_brier": (current.probability - current.outcome) ** 2,
        }
        folds.append(fold)
    valid = [fold for fold in folds if fold["status"] == "evaluated"]
    comparison = {}
    if valid:
        for name in names:
            differences = [
                f["scores"][name]["probability_weighted"]["crps"]
                - f["scores"][name]["historical"]["crps"]
                for f in valid
            ]
            comparison[name] = {
                "independent_events": len(valid),
                "mean_crps_difference": sum(differences) / len(valid),
                "paired_event_bootstrap95": paired_interval(differences),
                "negative_difference_favors": "probability_weighted",
            }
    checksum = hashlib.sha256(
        json.dumps(dataset.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "status": "synthetic_only"
        if dataset.source_kind == "synthetic"
        else ("research_only" if valid else "insufficient_data"),
        "model_version": MODEL_VERSION,
        "dataset_sha256": checksum,
        "source_kind": dataset.source_kind,
        "definition": dataset.definition,
        "settings": {
            "min_train": min_train,
            "min_scenario": min_scenario,
            "shrinkage_strength": SHRINKAGE_STRENGTH,
            "minimum_effective_tail_observations": MIN_EFFECTIVE_TAIL_OBSERVATIONS,
            "bootstrap_repetitions": 1000,
            "bootstrap_seed": 42,
        },
        "evaluation_at": dataset.evaluation_at.isoformat(),
        "total_events": len(dataset.releases),
        "prepared_events": len(events),
        "evaluated_events": len(valid),
        "coverage": coverage,
        "folds": folds,
        "comparison": comparison,
        "promotion_status": "not_evaluated",
        "limitations": [
            "Fixed-threshold binary pooled empirical benchmark; not a surprise regression",
            "Regime shifts and short event windows require verified real intraday data",
            "Tail risk is exploratory only after ten effective tail observations",
            "No conventional-expectations or volatility benchmark comparison yet",
            "Independent-event bootstrap assumes no serial dependence",
            "Predictive dispersion is not realized-volatility forecast validation",
            "No automatic production promotion or trading",
        ],
    }

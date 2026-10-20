"""Research-only, point-in-time A/B comparison on archived price and indicator inputs."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime

from shockgraph_risk.daily import (
    PriceSnapshot,
    _paired_block_interval,
    _utc,
    build_snapshot_forecasts,
    label_snapshot_forecasts,
)
from shockgraph_risk.macro_panel import MacroRiskPanel, TraditionalFeatureRow

_FLOOR = 1e-6
_PENALTY = 10.0


@dataclass(frozen=True, slots=True)
class TraditionalModelReport:
    horizon: int
    status: str
    reason: str | None
    holdout_start: datetime
    evaluation_at: datetime
    indicator_names: tuple[str, ...]
    training_count: int
    last_training_label_at: datetime | None
    baseline_labeled_holdout_count: int
    matched_holdout_count: int
    nonoverlapping_window_count: int
    first_matched_prediction_at: datetime | None
    last_matched_prediction_at: datetime | None
    trailing_mae: float | None
    ewma_mae: float | None
    traditional_mae: float | None
    trailing_qlike: float | None
    ewma_qlike: float | None
    traditional_qlike: float | None
    traditional_minus_ewma_mae_ci: tuple[float, float] | None
    traditional_minus_trailing_mae_ci: tuple[float, float] | None
    coefficients: tuple[float, ...] | None
    feature_means: tuple[float, ...] | None
    feature_scales: tuple[float, ...] | None
    training_input_sha256: str | None
    holdout_input_sha256: str | None
    training_label_snapshot_hash: str | None
    evaluation_label_snapshot_hash: str | None
    public_performance_allowed: bool = False


def _features(row: TraditionalFeatureRow) -> tuple[float, ...]:
    return (
        math.log(max(row.forecast.trailing_volatility, _FLOOR)),
        math.log(max(row.forecast.ewma_volatility, _FLOOR)),
        *(indicator.value for indicator in row.indicators),
    )


def _solve_ridge(
    features: Sequence[tuple[float, ...]], labels: Sequence[float]
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    """Fit standardized log volatility; the intercept alone is unpenalized."""
    count = len(labels)
    dimension = len(features[0])
    means = tuple(math.fsum(row[j] for row in features) / count for j in range(dimension))
    scales = tuple(
        max(math.sqrt(math.fsum((row[j] - means[j]) ** 2 for row in features) / count), _FLOOR)
        for j in range(dimension)
    )
    design = [
        (1.0, *((row[j] - means[j]) / scales[j] for j in range(dimension)))
        for row in features
    ]
    size = dimension + 1
    matrix = [[math.fsum(row[i] * row[j] for row in design) for j in range(size)]
              for i in range(size)]
    for index in range(1, size):
        matrix[index][index] += _PENALTY
    rhs = [math.fsum(row[i] * value for row, value in zip(design, labels, strict=True))
           for i in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(matrix[row][column]))
        if abs(matrix[pivot][column]) < 1e-12:
            raise ValueError("traditional model matrix is singular")
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        rhs[column], rhs[pivot] = rhs[pivot], rhs[column]
        for row in range(column + 1, size):
            factor = matrix[row][column] / matrix[column][column]
            for index in range(column, size):
                matrix[row][index] -= factor * matrix[column][index]
            rhs[row] -= factor * rhs[column]
    coefficients = [0.0] * size
    for row in range(size - 1, -1, -1):
        coefficients[row] = (
            rhs[row] - math.fsum(matrix[row][j] * coefficients[j]
                                 for j in range(row + 1, size))
        ) / matrix[row][row]
    return tuple(coefficients), means, scales


def _input_hash(rows: Sequence[TraditionalFeatureRow]) -> str:
    evidence = []
    for row in rows:
        forecast = row.forecast
        evidence.append(
            f"{forecast.session_date}:{forecast.prediction_at.isoformat()}:"
            f"{forecast.input_fingerprint}:{forecast.trailing_volatility}:"
            f"{forecast.ewma_volatility}"
        )
        evidence.extend(
            f"{indicator.name}:{indicator.source}:{indicator.observed_at.isoformat()}:"
            f"{indicator.available_at.isoformat()}:{indicator.value}:{indicator.raw_hash}"
            for indicator in row.indicators
        )
    return hashlib.sha256("\n".join(evidence).encode("utf-8")).hexdigest()


def _qlike(predicted: float, actual: float) -> float:
    variance = max(predicted * predicted, 1e-12)
    return math.log(variance) + actual * actual / variance


def evaluate_traditional_holdout(
    panel: MacroRiskPanel,
    snapshots: Sequence[PriceSnapshot],
    expected_sessions: Sequence[date],
    prediction_times: Mapping[date, datetime],
    *,
    holdout_start: datetime,
    evaluation_at: datetime,
    indicator_names: tuple[str, ...],
    min_training: int = 100,
    bootstrap_repeats: int = 1000,
) -> TraditionalModelReport:
    """Train using a pre-holdout label vintage; compare B and A on matched holdout days.

    The report stays private even with actual data: supplied capture times and rights need
    independent verification. A missing Kalshi probability never affects this comparison.
    """
    holdout_start = _utc(holdout_start, "holdout_start")
    evaluation_at = _utc(evaluation_at, "evaluation_at")
    if (not indicator_names or any(not name for name in indicator_names)
            or len(set(indicator_names)) != len(indicator_names)):
        raise ValueError("indicator_names must be fixed, nonempty, and unique")
    if min_training < 2 or bootstrap_repeats < 100:
        raise ValueError("min_training >= 2 and bootstrap_repeats >= 100 are required")
    if not prediction_times or (holdout_start not in prediction_times.values()
                                or evaluation_at < max(prediction_times.values())):
        raise ValueError("holdout must start on a prediction time and evaluation must follow")
    if not snapshots:
        raise ValueError("archived price snapshots are required")
    if snapshots[-1].captured_at > evaluation_at:
        raise ValueError("future snapshot cannot be used for evaluation")
    baseline = panel.baseline_rows
    if not baseline:
        raise ValueError("price baseline is empty")
    horizon = baseline[0].horizon
    recomputed = build_snapshot_forecasts(
        snapshots, expected_sessions, prediction_times, horizon=horizon
    )
    if recomputed != baseline:
        raise ValueError("panel baseline must match the archived price snapshots")
    by_forecast = set(baseline)
    traditional = panel.traditional_rows
    if len({row.forecast.session_date for row in traditional}) != len(traditional):
        raise ValueError("duplicate traditional forecast")
    if any(later.forecast.prediction_at <= earlier.forecast.prediction_at
           for earlier, later in zip(traditional, traditional[1:], strict=False)):
        raise ValueError("traditional rows must be in time order")
    for row in traditional:
        if row.forecast not in by_forecast:
            raise ValueError("traditional row must match an archived price forecast")
        if tuple(item.name for item in row.indicators) != indicator_names:
            raise ValueError("traditional row has unexpected indicators or order")
        if any(item.observed_at > row.forecast.prediction_at
               or item.available_at > row.forecast.prediction_at for item in row.indicators):
            raise ValueError("future indicator in traditional row")

    train_labels = {
        row.forecast.session_date: row
        for row in label_snapshot_forecasts(
            baseline, snapshots, expected_sessions, evaluation_at=holdout_start
        )
        if row.forecast.prediction_at < holdout_start and row.label_end_at < holdout_start
        and row.label_available_at <= holdout_start
    }
    holdout_labels = {
        row.forecast.session_date: row
        for row in label_snapshot_forecasts(
            baseline, snapshots, expected_sessions, evaluation_at=evaluation_at
        )
        if row.forecast.prediction_at >= holdout_start
    }
    training = tuple((row, train_labels[row.forecast.session_date]) for row in traditional
                     if row.forecast.session_date in train_labels)
    matched = tuple((row, holdout_labels[row.forecast.session_date]) for row in traditional
                    if row.forecast.session_date in holdout_labels)
    blocks = len(matched) // horizon
    reason = None
    if len(training) < min_training:
        reason = "insufficient_purged_training"
    elif blocks < 2:
        reason = "insufficient_nonoverlapping_holdout_windows"

    report = TraditionalModelReport(
        horizon=horizon, status="blocked" if reason else "evaluated_research_only",
        reason=reason, holdout_start=holdout_start, evaluation_at=evaluation_at,
        indicator_names=indicator_names, training_count=len(training),
        last_training_label_at=max((label.label_end_at for _, label in training), default=None),
        baseline_labeled_holdout_count=len(holdout_labels), matched_holdout_count=len(matched),
        nonoverlapping_window_count=blocks,
        first_matched_prediction_at=matched[0][0].forecast.prediction_at if matched else None,
        last_matched_prediction_at=matched[-1][0].forecast.prediction_at if matched else None,
        training_input_sha256=_input_hash([row for row, _ in training]) if training else None,
        holdout_input_sha256=_input_hash([row for row, _ in matched]) if matched else None,
        training_label_snapshot_hash=(training[0][1].label_snapshot_hash if training else None),
        evaluation_label_snapshot_hash=(matched[0][1].label_snapshot_hash if matched else None),
        trailing_mae=None, ewma_mae=None, traditional_mae=None,
        trailing_qlike=None, ewma_qlike=None, traditional_qlike=None,
        traditional_minus_ewma_mae_ci=None, traditional_minus_trailing_mae_ci=None,
        coefficients=None, feature_means=None, feature_scales=None,
    )
    if reason is not None:
        return report

    coefficients, means, scales = _solve_ridge(
        [_features(row) for row, _ in training],
        [math.log(max(label.realized_volatility, _FLOOR)) for _, label in training],
    )
    errors: dict[str, list[float]] = {name: [] for name in ("trailing", "ewma", "traditional")}
    qlikes: dict[str, list[float]] = {name: [] for name in errors}
    for row, label in matched:
        values = _features(row)
        linear = coefficients[0] + math.fsum(
            coefficients[index + 1] * (values[index] - means[index]) / scales[index]
            for index in range(len(values))
        )
        try:
            candidate = max(math.exp(linear), _FLOOR)
        except OverflowError as error:
            raise ValueError("model produced a nonfinite volatility") from error
        if not math.isfinite(candidate):
            raise ValueError("model produced a nonfinite volatility")
        actual = label.realized_volatility
        predictions = {
            "trailing": row.forecast.trailing_volatility,
            "ewma": row.forecast.ewma_volatility,
            "traditional": candidate,
        }
        for name, predicted in predictions.items():
            errors[name].append(abs(predicted - actual))
            qlikes[name].append(_qlike(predicted, actual))
    count = len(matched)
    differences_ewma = [m - a for m, a in zip(errors["traditional"], errors["ewma"],
                                                strict=True)]
    differences_trailing = [m - a for m, a in zip(errors["traditional"], errors["trailing"],
                                                    strict=True)]
    return replace(
        report,
        trailing_mae=math.fsum(errors["trailing"]) / count,
        ewma_mae=math.fsum(errors["ewma"]) / count,
        traditional_mae=math.fsum(errors["traditional"]) / count,
        trailing_qlike=math.fsum(qlikes["trailing"]) / count,
        ewma_qlike=math.fsum(qlikes["ewma"]) / count,
        traditional_qlike=math.fsum(qlikes["traditional"]) / count,
        traditional_minus_ewma_mae_ci=_paired_block_interval(
            differences_ewma, block_length=horizon, repeats=bootstrap_repeats, seed=0
        ),
        traditional_minus_trailing_mae_ci=_paired_block_interval(
            differences_trailing, block_length=horizon, repeats=bootstrap_repeats, seed=0
        ),
        coefficients=coefficients, feature_means=means, feature_scales=scales,
    )

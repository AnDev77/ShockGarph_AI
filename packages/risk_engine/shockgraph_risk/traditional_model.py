"""Research-only, point-in-time A/B comparison on archived price and indicator inputs."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime

from shockgraph_risk.daily import (
    PriceSnapshot,
    _adjusted,
    _paired_block_interval,
    _snapshot_as_of,
    _utc,
    build_snapshot_forecasts,
    label_snapshot_forecasts,
)
from shockgraph_risk.garch import GarchParameters, fit_garch_11, forecast_garch_11
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
    price_ridge_mae: float | None
    traditional_mae: float | None
    garch_mae: float | None
    trailing_qlike: float | None
    ewma_qlike: float | None
    price_ridge_qlike: float | None
    traditional_qlike: float | None
    garch_qlike: float | None
    traditional_minus_ewma_mae_ci: tuple[float, float] | None
    traditional_minus_trailing_mae_ci: tuple[float, float] | None
    traditional_minus_price_ridge_mae_ci: tuple[float, float] | None
    traditional_minus_garch_mae_ci: tuple[float, float] | None
    coefficients: tuple[float, ...] | None
    feature_means: tuple[float, ...] | None
    feature_scales: tuple[float, ...] | None
    price_coefficients: tuple[float, ...] | None
    price_feature_means: tuple[float, ...] | None
    price_feature_scales: tuple[float, ...] | None
    garch_parameters: GarchParameters | None
    garch_training_return_count: int | None
    garch_training_price_snapshot_hash: str | None
    garch_reason: str | None
    training_input_sha256: str | None
    holdout_input_sha256: str | None
    price_training_input_sha256: str | None
    price_holdout_input_sha256: str | None
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
            f"{indicator.name}:{indicator.source}:"
            f"{indicator.observed_at.isoformat() if indicator.observed_at else ''}:"
            f"{indicator.observation_date.isoformat() if indicator.observation_date else ''}:"
            f"{indicator.available_at.isoformat()}:{indicator.value}:{indicator.raw_hash}"
            for indicator in row.indicators
        )
    return hashlib.sha256("\n".join(evidence).encode("utf-8")).hexdigest()


def _price_input_hash(rows: Sequence[TraditionalFeatureRow]) -> str:
    evidence = (
        f"{row.forecast.session_date}:{row.forecast.prediction_at.isoformat()}:"
        f"{row.forecast.input_fingerprint}:{row.forecast.trailing_volatility}:"
        f"{row.forecast.ewma_volatility}"
        for row in rows
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
    min_garch_returns: int = 100,
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
    if min_training < 2 or min_garch_returns < 30 or bootstrap_repeats < 100:
        raise ValueError("min_training >= 2, min_garch_returns >= 30, and 100 bootstraps required")
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
        if any(not item.known_at(row.forecast.prediction_at) for item in row.indicators):
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
        price_training_input_sha256=(_price_input_hash([row for row, _ in training])
                                     if training else None),
        price_holdout_input_sha256=(_price_input_hash([row for row, _ in matched])
                                   if matched else None),
        training_label_snapshot_hash=(training[0][1].label_snapshot_hash if training else None),
        evaluation_label_snapshot_hash=(matched[0][1].label_snapshot_hash if matched else None),
        trailing_mae=None, ewma_mae=None, price_ridge_mae=None,
        traditional_mae=None, garch_mae=None,
        trailing_qlike=None, ewma_qlike=None, price_ridge_qlike=None,
        traditional_qlike=None, garch_qlike=None,
        traditional_minus_ewma_mae_ci=None, traditional_minus_trailing_mae_ci=None,
        traditional_minus_price_ridge_mae_ci=None, traditional_minus_garch_mae_ci=None,
        coefficients=None, feature_means=None, feature_scales=None,
        price_coefficients=None, price_feature_means=None, price_feature_scales=None,
        garch_parameters=None, garch_training_return_count=None,
        garch_training_price_snapshot_hash=None, garch_reason=None,
    )
    if reason is not None:
        return report

    labels = [math.log(max(label.realized_volatility, _FLOOR)) for _, label in training]
    price_coefficients, price_means, price_scales = _solve_ridge(
        [_features(row)[:2] for row, _ in training], labels,
    )
    coefficients, means, scales = _solve_ridge(
        [_features(row) for row, _ in training],
        labels,
    )

    # Fit GARCH once before the holdout on the price version available at that time.
    # The holdout session's own return must not enter the fit. At each later origin,
    # filter the fitted model using only that origin's archived full-price version.
    holdout_day = next(day for day, at in prediction_times.items() if at == holdout_start)
    offsets = {day: index for index, day in enumerate(expected_sessions)}
    training_prices = _snapshot_as_of(snapshots, holdout_start).prices[:offsets[holdout_day]]
    training_logs = [math.log(_adjusted(row)) for row in training_prices]
    training_returns = tuple(later - prior for prior, later in zip(
        training_logs, training_logs[1:], strict=False
    ))
    garch_reason = None
    garch_parameters = None
    if len(training_returns) < min_garch_returns:
        garch_reason = "insufficient_training_returns"
    else:
        try:
            garch_parameters = fit_garch_11(training_returns, min_returns=min_garch_returns)
        except ValueError as error:
            if str(error) not in {"degenerate_training_returns", "garch_fit_did_not_converge"}:
                raise
            garch_reason = str(error)

    names = ("trailing", "ewma", "price_ridge", "traditional")
    if garch_parameters is not None:
        names += ("garch",)
    errors: dict[str, list[float]] = {name: [] for name in names}
    qlikes: dict[str, list[float]] = {name: [] for name in errors}
    for row, label in matched:
        values = _features(row)
        price_linear = price_coefficients[0] + math.fsum(
            price_coefficients[index + 1] * (values[index] - price_means[index])
            / price_scales[index] for index in range(2)
        )
        linear = coefficients[0] + math.fsum(
            coefficients[index + 1] * (values[index] - means[index]) / scales[index]
            for index in range(len(values))
        )
        try:
            candidate = max(math.exp(linear), _FLOOR)
            price_candidate = max(math.exp(price_linear), _FLOOR)
        except OverflowError as error:
            raise ValueError("model produced a nonfinite volatility") from error
        if not math.isfinite(candidate) or not math.isfinite(price_candidate):
            raise ValueError("model produced a nonfinite volatility")
        actual = label.realized_volatility
        predictions = {
            "trailing": row.forecast.trailing_volatility,
            "ewma": row.forecast.ewma_volatility,
            "price_ridge": price_candidate,
            "traditional": candidate,
        }
        if garch_parameters is not None:
            observed = _snapshot_as_of(snapshots, row.forecast.prediction_at).prices
            if len(observed) != offsets[row.forecast.session_date] + 1:
                raise ValueError("no complete price snapshot available at prediction_at")
            logs = [math.log(_adjusted(price)) for price in observed]
            returns = tuple(later - prior for prior, later in zip(logs, logs[1:], strict=False))
            predictions["garch"] = forecast_garch_11(
                returns, garch_parameters, horizon=horizon
            )
        for name, predicted in predictions.items():
            errors[name].append(abs(predicted - actual))
            qlikes[name].append(_qlike(predicted, actual))
    count = len(matched)
    differences_ewma = [m - a for m, a in zip(errors["traditional"], errors["ewma"],
                                                strict=True)]
    differences_trailing = [m - a for m, a in zip(errors["traditional"], errors["trailing"],
                                                    strict=True)]
    differences_price = [m - a for m, a in zip(errors["traditional"],
                                               errors["price_ridge"], strict=True)]
    differences_garch = ([m - a for m, a in zip(errors["traditional"],
                                                errors["garch"], strict=True)]
                         if garch_parameters else [])
    return replace(
        report,
        trailing_mae=math.fsum(errors["trailing"]) / count,
        ewma_mae=math.fsum(errors["ewma"]) / count,
        price_ridge_mae=math.fsum(errors["price_ridge"]) / count,
        traditional_mae=math.fsum(errors["traditional"]) / count,
        garch_mae=math.fsum(errors["garch"]) / count if garch_parameters else None,
        trailing_qlike=math.fsum(qlikes["trailing"]) / count,
        ewma_qlike=math.fsum(qlikes["ewma"]) / count,
        price_ridge_qlike=math.fsum(qlikes["price_ridge"]) / count,
        traditional_qlike=math.fsum(qlikes["traditional"]) / count,
        garch_qlike=math.fsum(qlikes["garch"]) / count if garch_parameters else None,
        traditional_minus_ewma_mae_ci=_paired_block_interval(
            differences_ewma, block_length=horizon, repeats=bootstrap_repeats, seed=0
        ),
        traditional_minus_trailing_mae_ci=_paired_block_interval(
            differences_trailing, block_length=horizon, repeats=bootstrap_repeats, seed=0
        ),
        traditional_minus_price_ridge_mae_ci=_paired_block_interval(
            differences_price, block_length=horizon, repeats=bootstrap_repeats, seed=0
        ),
        traditional_minus_garch_mae_ci=(_paired_block_interval(
            differences_garch, block_length=horizon, repeats=bootstrap_repeats, seed=0
        ) if garch_parameters else None),
        coefficients=coefficients, feature_means=means, feature_scales=scales,
        price_coefficients=price_coefficients, price_feature_means=price_means,
        price_feature_scales=price_scales, garch_parameters=garch_parameters,
        garch_training_return_count=len(training_returns),
        garch_training_price_snapshot_hash=(
            _snapshot_as_of(snapshots, holdout_start).prices[0].raw_payload_hash
        ),
        garch_reason=garch_reason,
    )

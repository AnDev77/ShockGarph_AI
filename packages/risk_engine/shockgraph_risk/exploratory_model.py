"""Fixed, price-only research model on one current adjusted-close history.

The adjusted prices have no verified historical vintages. This module must never
be used to serve a live or publicly claimed forecast.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from shockgraph_risk.daily import _paired_block_interval
from shockgraph_risk.exploratory_history import HistoryPrice

_MIN_TRAINING = 100
_RIDGE_PENALTY = 10.0
_FLOOR = 1e-6


@dataclass(frozen=True, slots=True)
class ExploratoryModelPoint:
    session_date: date
    observed_volatility: float
    ewma_volatility: float
    ridge_volatility: float


@dataclass(frozen=True, slots=True)
class ModelComparison:
    horizon: int
    status: str
    training_count: int
    last_training_label_date: date | None
    holdout_count: int
    nonoverlapping_window_count: int
    first_holdout_date: date | None
    last_holdout_date: date | None
    trailing_mae: float | None
    ewma_mae: float | None
    ridge_mae: float | None
    trailing_qlike: float | None
    ewma_qlike: float | None
    ridge_qlike: float | None
    ridge_minus_trailing_mae_ci: tuple[float, float] | None
    ridge_minus_ewma_mae_ci: tuple[float, float] | None
    coefficients: tuple[float, ...] | None
    points: tuple[ExploratoryModelPoint, ...] = ()


def _solve_ridge(features: list[tuple[float, float, float]], labels: list[float]) -> tuple[
    tuple[float, ...], tuple[float, ...], tuple[float, ...]
]:
    """Standardize on training rows only and solve intercept plus ridge coefficients."""
    count = len(labels)
    means = tuple(math.fsum(row[j] for row in features) / count for j in range(3))
    scales = tuple(
        max(math.sqrt(math.fsum((row[j] - means[j]) ** 2 for row in features) / count), _FLOOR)
        for j in range(3)
    )
    design = [
        (1.0, *((row[j] - means[j]) / scales[j] for j in range(3)))
        for row in features
    ]
    matrix = [
        [math.fsum(row[i] * row[j] for row in design) for j in range(4)]
        for i in range(4)
    ]
    for i in range(1, 4):
        matrix[i][i] += _RIDGE_PENALTY
    rhs = [math.fsum(row[i] * value for row, value in zip(design, labels, strict=True))
           for i in range(4)]
    for column in range(4):
        pivot = max(range(column, 4), key=lambda row: abs(matrix[row][column]))
        if abs(matrix[pivot][column]) < 1e-12:
            raise ValueError("ridge system is singular")
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        rhs[column], rhs[pivot] = rhs[pivot], rhs[column]
        for row in range(column + 1, 4):
            factor = matrix[row][column] / matrix[column][column]
            for j in range(column, 4):
                matrix[row][j] -= factor * matrix[column][j]
            rhs[row] -= factor * rhs[column]
    coefficients = [0.0] * 4
    for row in range(3, -1, -1):
        coefficients[row] = (
            rhs[row] - math.fsum(matrix[row][j] * coefficients[j] for j in range(row + 1, 4))
        ) / matrix[row][row]
    return tuple(coefficients), means, scales


def _features(squares: Sequence[float], index: int) -> tuple[float, float, float]:
    def volatility(window: int) -> float:
        return math.log(
            max(math.sqrt(math.fsum(squares[index - window : index]) / window), _FLOOR)
        )

    return volatility(1), volatility(5), volatility(20)


def _qlike(predicted: float, actual: float) -> float:
    variance = max(predicted * predicted, 1e-12)
    return math.log(variance) + actual * actual / variance


def compare_price_only_model(
    prices: Sequence[HistoryPrice],
    *,
    holdout_start: date,
    horizons: tuple[int, ...] = (5, 20),
    bootstrap_repeats: int = 1000,
) -> tuple[ModelComparison, ...]:
    """Fit once before holdout; score a fixed model on shared future windows."""
    if not horizons or len(set(horizons)) != len(horizons) or any(h < 2 for h in horizons):
        raise ValueError("horizons must be unique and at least two sessions")
    if bootstrap_repeats < 100:
        raise ValueError("bootstrap_repeats must be at least 100")
    if not prices:
        raise ValueError("price history is empty")
    dates = [row.session_date for row in prices]
    if any(b <= a for a, b in zip(dates, dates[1:], strict=False)):
        raise ValueError("price dates must be unique and increasing")
    if any(not math.isfinite(row.adjusted_close) or row.adjusted_close <= 0 for row in prices):
        raise ValueError("adjusted closes must be positive and finite")
    if holdout_start <= dates[0] or holdout_start > dates[-1]:
        raise ValueError("holdout_start must follow the first date and not exceed the last")
    logs = [math.log(row.adjusted_close) for row in prices]
    squares = [(b - a) ** 2 for a, b in zip(logs, logs[1:], strict=False)]
    reports = []
    for horizon in horizons:
        examples = []
        holdout_indices = []
        for index in range(20, len(prices) - horizon):
            if dates[index] >= holdout_start:
                holdout_indices.append(index)
            elif dates[index + horizon] < holdout_start:
                examples.append(index)
        n = len(holdout_indices)
        blocks = n // horizon
        training_end = dates[examples[-1] + horizon] if examples else None
        if len(examples) < _MIN_TRAINING or blocks < 2:
            reports.append(ModelComparison(
                horizon=horizon,
                status="insufficient_training_or_holdout",
                training_count=len(examples),
                last_training_label_date=training_end,
                holdout_count=n,
                nonoverlapping_window_count=blocks,
                first_holdout_date=dates[holdout_indices[0]] if n else None,
                last_holdout_date=dates[holdout_indices[-1]] if n else None,
                trailing_mae=None, ewma_mae=None, ridge_mae=None,
                trailing_qlike=None, ewma_qlike=None, ridge_qlike=None,
                ridge_minus_trailing_mae_ci=None, ridge_minus_ewma_mae_ci=None,
                coefficients=None,
            ))
            continue
        features = [_features(squares, i) for i in examples]
        labels = [
            math.log(max(math.sqrt(math.fsum(squares[i : i + horizon]) / horizon), _FLOOR))
            for i in examples
        ]
        coefficients, means, scales = _solve_ridge(features, labels)
        # Identical EWMA recursion and target definition to the existing baseline.
        alpha = 2 / (horizon + 1)
        ewma_variance = math.fsum(squares[:horizon]) / horizon
        errors: dict[str, list[float]] = {name: [] for name in ("trailing", "ewma", "ridge")}
        qlikes: dict[str, list[float]] = {name: [] for name in errors}
        points = []
        for index in range(horizon, len(prices) - horizon):
            if index > horizon:
                ewma_variance = alpha * squares[index - 1] + (1 - alpha) * ewma_variance
            if dates[index] < holdout_start or index < 20:
                continue
            input_values = _features(squares, index)
            linear = coefficients[0] + math.fsum(
                coefficients[j + 1] * (input_values[j] - means[j]) / scales[j]
                for j in range(3)
            )
            candidate = max(math.exp(linear), _FLOOR)
            actual = math.sqrt(math.fsum(squares[index : index + horizon]) / horizon)
            forecasts = {
                "trailing": math.sqrt(math.fsum(squares[index - horizon : index]) / horizon),
                "ewma": math.sqrt(ewma_variance),
                "ridge": candidate,
            }
            points.append(ExploratoryModelPoint(
                session_date=dates[index], observed_volatility=actual,
                ewma_volatility=forecasts["ewma"], ridge_volatility=candidate,
            ))
            for name, predicted in forecasts.items():
                errors[name].append(abs(predicted - actual))
                qlikes[name].append(_qlike(predicted, actual))
        paired_trailing = [m - b for m, b in zip(errors["ridge"], errors["trailing"], strict=True)]
        paired_ewma = [m - b for m, b in zip(errors["ridge"], errors["ewma"], strict=True)]
        reports.append(ModelComparison(
            horizon=horizon,
            status="exploratory_current_history_only",
            training_count=len(examples),
            last_training_label_date=training_end,
            holdout_count=n,
            nonoverlapping_window_count=blocks,
            first_holdout_date=dates[holdout_indices[0]] if n else None,
            last_holdout_date=dates[holdout_indices[-1]] if n else None,
            trailing_mae=math.fsum(errors["trailing"]) / n,
            ewma_mae=math.fsum(errors["ewma"]) / n,
            ridge_mae=math.fsum(errors["ridge"]) / n,
            trailing_qlike=math.fsum(qlikes["trailing"]) / n,
            ewma_qlike=math.fsum(qlikes["ewma"]) / n,
            ridge_qlike=math.fsum(qlikes["ridge"]) / n,
            ridge_minus_trailing_mae_ci=_paired_block_interval(
                paired_trailing, block_length=horizon, repeats=bootstrap_repeats, seed=0
            ),
            ridge_minus_ewma_mae_ci=_paired_block_interval(
                paired_ewma, block_length=horizon, repeats=bootstrap_repeats, seed=0
            ),
            coefficients=coefficients,
            points=tuple(points),
        ))
    return tuple(reports)

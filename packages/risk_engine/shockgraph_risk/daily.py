from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from shockgraph_domain.records import AssetPriceRecord


@dataclass(frozen=True, slots=True)
class VolatilityForecast:
    symbol: str
    session_date: date
    prediction_at: datetime
    horizon: int
    trailing_volatility: float
    ewma_volatility: float


@dataclass(frozen=True, slots=True)
class LabeledForecast:
    forecast: VolatilityForecast
    label_end_at: datetime
    label_available_at: datetime
    realized_volatility: float


@dataclass(frozen=True, slots=True)
class BaselineReport:
    horizon: int
    sample_size: int
    first_prediction_at: datetime
    last_prediction_at: datetime
    trailing_mae: float
    ewma_mae: float
    trailing_qlike: float
    ewma_qlike: float
    ewma_minus_trailing_mae: float
    paired_mae_ci: tuple[float, float] | None
    bootstrap_block_length: int


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value.astimezone(UTC)


def _ordered_prices(
    prices: Sequence[AssetPriceRecord], expected_sessions: Sequence[date]
) -> tuple[AssetPriceRecord, ...]:
    sessions = tuple(expected_sessions)
    if not sessions or tuple(sorted(set(sessions))) != sessions:
        raise ValueError("expected_sessions must be nonempty, unique, and increasing")
    if len(prices) != len(sessions):
        raise ValueError("every expected session needs exactly one price")
    ordered = tuple(sorted(prices, key=lambda row: row.session_date))
    if tuple(row.session_date for row in ordered) != sessions:
        raise ValueError("price sessions must match the independent expected_sessions calendar")
    first = ordered[0]
    for index, row in enumerate(ordered):
        if (row.symbol, row.venue, row.currency, row.source) != (
            first.symbol, first.venue, first.currency, first.source
        ):
            raise ValueError("a daily price series must have one asset, currency, and source")
        if row.adjusted_close is None or row.available_at is None:
            raise ValueError("adjusted_close and its exact available_at are required")
        if index and row.observed_at <= ordered[index - 1].observed_at:
            raise ValueError("price observation times must increase with sessions")
    return ordered


def _adjusted(row: AssetPriceRecord) -> float:
    if row.adjusted_close is None:
        raise ValueError("adjusted_close is required")
    value = float(row.adjusted_close)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("adjusted_close must be finite and positive as a float")
    return value


def _available(row: AssetPriceRecord) -> datetime:
    if row.available_at is None:
        raise ValueError("exact available_at is required")
    return row.available_at


def _squared_log_returns(prices: Sequence[AssetPriceRecord]) -> tuple[float, ...]:
    adjusted = [_adjusted(row) for row in prices]
    return tuple(
        (math.log(current) - math.log(prior)) ** 2
        for prior, current in zip(adjusted, adjusted[1:], strict=False)
    )


def build_baseline_forecasts(
    prices: Sequence[AssetPriceRecord],
    expected_sessions: Sequence[date],
    prediction_times: Mapping[date, datetime],
    *,
    horizon: int,
) -> tuple[VolatilityForecast, ...]:
    """Forecast at t using prices available at t; no future return enters a baseline."""
    if horizon < 2:
        raise ValueError("horizon must be at least 2 trading days")
    ordered = _ordered_prices(prices, expected_sessions)
    sessions = tuple(expected_sessions)
    if set(prediction_times) != set(sessions):
        raise ValueError("one explicit prediction time is required for every expected session")
    times = tuple(_utc(prediction_times[session], "prediction_at") for session in sessions)
    if any(later <= earlier for earlier, later in zip(times, times[1:], strict=False)):
        raise ValueError("prediction times must increase with sessions")
    squares = _squared_log_returns(ordered)
    if len(ordered) <= horizon:
        return ()

    # Seed from the first h known returns, then update once with each newly available return.
    alpha = 2 / (horizon + 1)
    ewma_variance = math.fsum(squares[:horizon]) / horizon
    forecasts = []
    for index in range(horizon, len(ordered)):
        if index > horizon:
            ewma_variance = alpha * squares[index - 1] + (1 - alpha) * ewma_variance
        prediction_at = times[index]
        if any(_available(row) > prediction_at for row in ordered[: index + 1]):
            raise ValueError("a baseline uses a price version unavailable at prediction_at")
        trailing_variance = math.fsum(squares[index - horizon : index]) / horizon
        forecasts.append(
            VolatilityForecast(
                symbol=ordered[index].symbol,
                session_date=sessions[index],
                prediction_at=prediction_at,
                horizon=horizon,
                trailing_volatility=math.sqrt(trailing_variance),
                ewma_volatility=math.sqrt(ewma_variance),
            )
        )
    return tuple(forecasts)


def label_forecasts(
    forecasts: Sequence[VolatilityForecast],
    prices: Sequence[AssetPriceRecord],
    expected_sessions: Sequence[date],
    *,
    evaluation_at: datetime,
) -> tuple[LabeledForecast, ...]:
    """Attach only labels whose full future price window is available for evaluation."""
    evaluation_at = _utc(evaluation_at, "evaluation_at")
    ordered = _ordered_prices(prices, expected_sessions)
    offsets = {price.session_date: index for index, price in enumerate(ordered)}
    squares = _squared_log_returns(ordered)
    labeled = []
    for forecast in forecasts:
        if forecast.symbol != ordered[0].symbol:
            raise ValueError("forecast and prices refer to different assets")
        if forecast.session_date not in offsets or forecast.horizon < 2:
            raise ValueError("forecast does not match the price calendar")
        index = offsets[forecast.session_date]
        end = index + forecast.horizon
        if end >= len(ordered):
            continue
        future = ordered[index + 1 : end + 1]
        label_available_at = max(_available(row) for row in ordered[index : end + 1])
        if label_available_at > evaluation_at:
            continue
        label_end_at = future[-1].observed_at
        if label_end_at <= forecast.prediction_at:
            raise ValueError("label window must follow prediction_at")
        labeled.append(
            LabeledForecast(
                forecast=forecast,
                label_end_at=label_end_at,
                label_available_at=label_available_at,
                realized_volatility=math.sqrt(math.fsum(squares[index:end]) / forecast.horizon),
            )
        )
    return tuple(labeled)


def purged_training_rows(
    rows: Sequence[LabeledForecast], *, next_split_at: datetime
) -> tuple[LabeledForecast, ...]:
    """Keep only labels fully ended and available before the next split begins."""
    next_split_at = _utc(next_split_at, "next_split_at")
    return tuple(
        row
        for row in rows
        if row.forecast.prediction_at < next_split_at
        and row.label_end_at < next_split_at
        and row.label_available_at <= next_split_at
    )


def _quantile(sorted_values: Sequence[float], proportion: float) -> float:
    position = (len(sorted_values) - 1) * proportion
    low = math.floor(position)
    high = math.ceil(position)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def _paired_block_interval(
    differences: Sequence[float], *, block_length: int, repeats: int, seed: int
) -> tuple[float, float] | None:
    length = len(differences)
    if length < 2 * block_length:
        return None
    rng = random.Random(seed)
    estimates = []
    for _ in range(repeats):
        sampled = []
        while len(sampled) < length:
            start = rng.randrange(length)
            sampled.extend(differences[(start + offset) % length] for offset in range(block_length))
        estimates.append(math.fsum(sampled[:length]) / length)
    estimates.sort()
    return _quantile(estimates, 0.025), _quantile(estimates, 0.975)


def score_baselines(
    rows: Sequence[LabeledForecast], *, holdout_start: datetime, bootstrap_repeats: int = 1000
) -> BaselineReport:
    """Compare both forecasts on the exact same eligible holdout sessions."""
    holdout_start = _utc(holdout_start, "holdout_start")
    if bootstrap_repeats < 100:
        raise ValueError("bootstrap_repeats must be at least 100")
    selected = tuple(
        sorted(
            (row for row in rows if row.forecast.prediction_at >= holdout_start),
            key=lambda row: row.forecast.prediction_at,
        )
    )
    if not selected:
        raise ValueError("no labeled holdout forecasts")
    horizon = selected[0].forecast.horizon
    if any(row.forecast.horizon != horizon for row in selected):
        raise ValueError("all compared forecasts must have the same horizon")
    if len({row.forecast.prediction_at for row in selected}) != len(selected):
        raise ValueError("duplicate holdout sessions")

    trailing_errors, ewma_errors, trailing_qlike, ewma_qlike = [], [], [], []
    for row in selected:
        actual = row.realized_volatility
        trailing = row.forecast.trailing_volatility
        ewma = row.forecast.ewma_volatility
        if not all(math.isfinite(value) and value >= 0 for value in (actual, trailing, ewma)):
            raise ValueError("volatilities must be finite and nonnegative")
        trailing_errors.append(abs(trailing - actual))
        ewma_errors.append(abs(ewma - actual))
        # QLIKE is defined for strictly positive variance; disclose the common floor.
        actual_variance = actual * actual
        for prediction, output in ((trailing, trailing_qlike), (ewma, ewma_qlike)):
            variance = max(prediction * prediction, 1e-12)
            output.append(math.log(variance) + actual_variance / variance)

    differences = [new - old for new, old in zip(ewma_errors, trailing_errors, strict=True)]
    n = len(selected)
    return BaselineReport(
        horizon=horizon,
        sample_size=n,
        first_prediction_at=selected[0].forecast.prediction_at,
        last_prediction_at=selected[-1].forecast.prediction_at,
        trailing_mae=math.fsum(trailing_errors) / n,
        ewma_mae=math.fsum(ewma_errors) / n,
        trailing_qlike=math.fsum(trailing_qlike) / n,
        ewma_qlike=math.fsum(ewma_qlike) / n,
        ewma_minus_trailing_mae=math.fsum(differences) / n,
        paired_mae_ci=_paired_block_interval(
            differences, block_length=horizon, repeats=bootstrap_repeats, seed=0
        ),
        bootstrap_block_length=horizon,
    )

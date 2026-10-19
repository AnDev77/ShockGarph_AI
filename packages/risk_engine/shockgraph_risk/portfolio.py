from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from shockgraph_domain.portfolio import PortfolioValidationResult, Position, validate_positions
from shockgraph_domain.records import AssetPriceRecord

from shockgraph_risk.daily import (
    BaselineReport,
    LabeledForecast,
    VolatilityForecast,
    score_baselines,
)


@dataclass(frozen=True, slots=True)
class PortfolioForecast:
    positions: tuple[Position, ...]
    session_date: date
    prediction_at: datetime
    horizon: int
    trailing_volatility: float
    ewma_volatility: float


@dataclass(frozen=True, slots=True)
class LabeledPortfolioForecast:
    forecast: PortfolioForecast
    label_end_at: datetime
    label_available_at: datetime
    realized_volatility: float


@dataclass(frozen=True, slots=True)
class PortfolioBaselineReport:
    positions: tuple[Position, ...]
    metrics: BaselineReport


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value.astimezone(UTC)


def _panel(
    prices_by_symbol: Mapping[str, Sequence[AssetPriceRecord]],
    expected_sessions: Sequence[date],
    portfolio: PortfolioValidationResult,
) -> tuple[tuple[Position, ...], dict[str, tuple[AssetPriceRecord, ...]]]:
    positions = validate_positions(
        [{"symbol": position.symbol, "weight": position.weight} for position in portfolio.positions]
    ).positions
    sessions = tuple(expected_sessions)
    if not sessions or tuple(sorted(set(sessions))) != sessions:
        raise ValueError("expected_sessions must be nonempty, unique, and increasing")
    if set(prices_by_symbol) != {position.symbol for position in positions}:
        raise ValueError("price series must match portfolio positions exactly")

    ordered: dict[str, tuple[AssetPriceRecord, ...]] = {}
    currencies: set[str] = set()
    for position in positions:
        rows = tuple(sorted(prices_by_symbol[position.symbol], key=lambda row: row.session_date))
        if len(rows) != len(sessions) or tuple(row.session_date for row in rows) != sessions:
            raise ValueError("every asset needs exactly one price for every expected session")
        first = rows[0]
        if first.symbol != position.symbol:
            raise ValueError("price symbol does not match the position")
        for index, row in enumerate(rows):
            if (row.symbol, row.venue, row.currency, row.source) != (
                first.symbol,
                first.venue,
                first.currency,
                first.source,
            ):
                raise ValueError("each asset must have one symbol, venue, currency, and source")
            if row.adjusted_close is None or row.available_at is None:
                raise ValueError("adjusted_close and exact available_at are required")
            if index and row.observed_at <= rows[index - 1].observed_at:
                raise ValueError("asset observation times must increase with sessions")
        currencies.add(first.currency)
        ordered[position.symbol] = rows
    if currencies != {"USD"}:
        raise ValueError("the initial portfolio baseline requires all prices in USD")
    return positions, ordered


def _price(row: AssetPriceRecord) -> float:
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


def _joint_returns(
    positions: tuple[Position, ...], ordered: Mapping[str, tuple[AssetPriceRecord, ...]]
) -> tuple[float, ...]:
    """Log returns of a USD portfolio rebalanced to the stated weights each session."""
    length = len(next(iter(ordered.values())))
    result = []
    for index in range(1, length):
        simple_return = math.fsum(
            position.weight
            * (_price(ordered[position.symbol][index]) / _price(ordered[position.symbol][index - 1])
               - 1)
            for position in positions
        )
        if not math.isfinite(simple_return) or simple_return <= -1:
            raise ValueError("the weighted portfolio return must be finite and greater than -1")
        result.append(math.log1p(simple_return))
    return tuple(result)


def build_portfolio_forecasts(
    prices_by_symbol: Mapping[str, Sequence[AssetPriceRecord]],
    expected_sessions: Sequence[date],
    prediction_times: Mapping[date, datetime],
    portfolio: PortfolioValidationResult,
    *,
    horizon: int,
) -> tuple[PortfolioForecast, ...]:
    """Joint portfolio trailing/EWMA risk from aligned, already available price versions."""
    if horizon < 2:
        raise ValueError("horizon must be at least 2 trading days")
    positions, ordered = _panel(prices_by_symbol, expected_sessions, portfolio)
    sessions = tuple(expected_sessions)
    if set(prediction_times) != set(sessions):
        raise ValueError("one explicit prediction time is required for every expected session")
    times = tuple(_utc(prediction_times[session], "prediction_at") for session in sessions)
    if any(later <= earlier for earlier, later in zip(times, times[1:], strict=False)):
        raise ValueError("prediction times must increase with sessions")
    if len(sessions) <= horizon:
        return ()

    returns = _joint_returns(positions, ordered)
    squares = tuple(value * value for value in returns)
    alpha = 2 / (horizon + 1)
    ewma_variance = math.fsum(squares[:horizon]) / horizon
    forecasts = []
    latest_available = max(_available(ordered[position.symbol][0]) for position in positions)
    for index, session in enumerate(sessions):
        latest_available = max(
            latest_available,
            *(_available(ordered[position.symbol][index]) for position in positions),
        )
        if index < horizon:
            continue
        prediction_at = times[index]
        if latest_available > prediction_at:
            raise ValueError("a portfolio price version is unavailable at prediction_at")
        if index > horizon:
            ewma_variance = alpha * squares[index - 1] + (1 - alpha) * ewma_variance
        trailing_variance = math.fsum(squares[index - horizon : index]) / horizon
        forecasts.append(
            PortfolioForecast(
                positions=positions,
                session_date=session,
                prediction_at=prediction_at,
                horizon=horizon,
                trailing_volatility=math.sqrt(trailing_variance),
                ewma_volatility=math.sqrt(ewma_variance),
            )
        )
    return tuple(forecasts)


def label_portfolio_forecasts(
    forecasts: Sequence[PortfolioForecast],
    prices_by_symbol: Mapping[str, Sequence[AssetPriceRecord]],
    expected_sessions: Sequence[date],
    portfolio: PortfolioValidationResult,
    *,
    evaluation_at: datetime,
) -> tuple[LabeledPortfolioForecast, ...]:
    """Evaluate only complete future joint-return windows whose prices are all available."""
    evaluation_at = _utc(evaluation_at, "evaluation_at")
    positions, ordered = _panel(prices_by_symbol, expected_sessions, portfolio)
    sessions = tuple(expected_sessions)
    offsets = {session: index for index, session in enumerate(sessions)}
    returns = _joint_returns(positions, ordered)
    labels = []
    for forecast in forecasts:
        if (
            forecast.positions != positions
            or forecast.session_date not in offsets
            or forecast.horizon < 2
        ):
            raise ValueError("portfolio forecast does not match the price panel")
        _utc(forecast.prediction_at, "prediction_at")
        index = offsets[forecast.session_date]
        end = index + forecast.horizon
        if end >= len(sessions):
            continue
        price_window = (
            ordered[position.symbol][row_index]
            for position in positions
            for row_index in range(index, end + 1)
        )
        label_available_at = max(_available(row) for row in price_window)
        if label_available_at > evaluation_at:
            continue
        label_end_at = max(ordered[position.symbol][end].observed_at for position in positions)
        if label_end_at <= forecast.prediction_at:
            raise ValueError("label window must follow prediction_at")
        realized = math.sqrt(
            math.fsum(value * value for value in returns[index:end]) / forecast.horizon
        )
        labels.append(
            LabeledPortfolioForecast(
                forecast=forecast,
                label_end_at=label_end_at,
                label_available_at=label_available_at,
                realized_volatility=realized,
            )
        )
    return tuple(labels)


def purged_portfolio_training_rows(
    rows: Sequence[LabeledPortfolioForecast], *, next_split_at: datetime
) -> tuple[LabeledPortfolioForecast, ...]:
    next_split_at = _utc(next_split_at, "next_split_at")
    return tuple(
        row
        for row in rows
        if row.forecast.prediction_at < next_split_at
        and row.label_end_at < next_split_at
        and row.label_available_at <= next_split_at
    )


def score_portfolio_baselines(
    rows: Sequence[LabeledPortfolioForecast],
    *,
    holdout_start: datetime,
    bootstrap_repeats: int = 1000,
) -> PortfolioBaselineReport:
    """Apply the existing paired volatility scores to a single, fixed-weight portfolio."""
    if not rows:
        raise ValueError("no labeled portfolio forecasts")
    positions = rows[0].forecast.positions
    if any(row.forecast.positions != positions for row in rows):
        raise ValueError("all portfolio forecasts must use the same positions and weights")
    shared_rows = tuple(
        LabeledForecast(
            forecast=VolatilityForecast(
                symbol="PORTFOLIO",
                session_date=row.forecast.session_date,
                prediction_at=row.forecast.prediction_at,
                horizon=row.forecast.horizon,
                trailing_volatility=row.forecast.trailing_volatility,
                ewma_volatility=row.forecast.ewma_volatility,
            ),
            label_end_at=row.label_end_at,
            label_available_at=row.label_available_at,
            realized_volatility=row.realized_volatility,
        )
        for row in rows
    )
    return PortfolioBaselineReport(
        positions=positions,
        metrics=score_baselines(
            shared_rows, holdout_start=holdout_start, bootstrap_repeats=bootstrap_repeats
        ),
    )

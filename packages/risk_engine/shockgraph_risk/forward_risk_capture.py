"""Immutable, private as-of daily risk forecasts and delayed outcome scoring.

This module requires an externally archived full price vintage. Its records may
only be created before the next outcome session closes. No public model claim.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from shockgraph_data_pipeline.market_calendar import ScheduledSession, nasdaq_sessions

from shockgraph_risk.exploratory_history import HistoryPrice
from shockgraph_risk.garch import fit_garch_11, forecast_garch_11
from shockgraph_risk.gjr_garch import fit_gjr_garch_11, forecast_gjr_garch_11

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ForwardHorizon:
    horizon: int
    first_outcome_session: date
    last_outcome_session: date
    label_end_at: datetime
    trailing_volatility: float
    ewma_volatility: float
    garch_volatility: float
    gjr_volatility: float


@dataclass(frozen=True, slots=True)
class ForwardRiskRecord:
    symbol: str
    origin_session: date
    source_snapshot_sha256: str
    source_captured_at: datetime
    prediction_at: datetime
    horizons: tuple[ForwardHorizon, ...]
    public_performance_allowed: bool = False


@dataclass(frozen=True, slots=True)
class ForwardRiskScore:
    symbol: str
    origin_session: date
    horizon: int
    prediction_at: datetime
    label_end_at: datetime
    label_captured_at: datetime
    source_snapshot_sha256: str
    label_snapshot_sha256: str
    realized_volatility: float
    trailing_absolute_error: float
    ewma_absolute_error: float
    garch_absolute_error: float
    gjr_absolute_error: float
    public_performance_allowed: bool = False


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field} must be UTC")
    return value.astimezone(UTC)


def _prices(prices: Sequence[HistoryPrice]) -> tuple[HistoryPrice, ...]:
    rows = tuple(prices)
    if not rows or any(b.session_date <= a.session_date
                       for a, b in zip(rows, rows[1:], strict=False)):
        raise ValueError("prices must have unique increasing sessions")
    if any(not math.isfinite(row.adjusted_close) or row.adjusted_close <= 0 for row in rows):
        raise ValueError("prices must be positive and finite")
    sessions = nasdaq_sessions(rows[0].session_date, rows[-1].session_date)
    if tuple(item.session_date for item in sessions) != tuple(row.session_date for row in rows):
        raise ValueError("prices must cover the reviewed session calendar")
    return rows


def _outcome_sessions(origin: date, horizon: int) -> tuple[ScheduledSession, ...]:
    if horizon not in (5, 20):
        raise ValueError("forward risk supports only five or twenty sessions")
    # The reviewed calendar ends in 2026. Extend and reverify it before 2027.
    sessions = nasdaq_sessions(origin + timedelta(days=1), date(2026, 12, 31))
    if len(sessions) < horizon:
        raise ValueError("reviewed future calendar is too short")
    return sessions[:horizon]


def _digest(value: str) -> str:
    if not _SHA256.fullmatch(value):
        raise ValueError("snapshot SHA-256 must be lowercase hex")
    return value


def build_forward_risk_record(
    symbol: str,
    prices: Sequence[HistoryPrice],
    *,
    source_snapshot_sha256: str,
    source_captured_at: datetime,
    prediction_at: datetime,
) -> ForwardRiskRecord:
    """Forecast from a completed session's price vintage before the next close."""
    if symbol not in ("TLT", "SPY"):
        raise ValueError("forward risk supports TLT and SPY")
    source_captured_at = _utc(source_captured_at, "source_captured_at")
    prediction_at = _utc(prediction_at, "prediction_at")
    rows = _prices(prices)
    origin = rows[-1].session_date
    origin_close = nasdaq_sessions(origin, origin)[0].close_at
    next_session = _outcome_sessions(origin, 20)[0]
    if prediction_at < source_captured_at or source_captured_at < origin_close:
        raise ValueError("prediction needs a completed and available capture")
    if prediction_at >= next_session.close_at:
        raise ValueError("prediction must precede the next outcome close")
    if len(rows) < 101:
        raise ValueError("insufficient past price sessions")

    snapshot_sha = _digest(source_snapshot_sha256)
    logs = [math.log(row.adjusted_close) for row in rows]
    returns = tuple(b - a for a, b in zip(logs, logs[1:], strict=False))
    squares = tuple(value * value for value in returns)
    garch = fit_garch_11(returns)
    gjr = fit_gjr_garch_11(returns)
    targets = []
    for horizon in (5, 20):
        future = _outcome_sessions(origin, horizon)
        trailing = math.sqrt(math.fsum(squares[-horizon:]) / horizon)
        alpha = 2 / (horizon + 1)
        ewma = math.fsum(squares[:horizon]) / horizon
        for squared in squares[horizon:]:
            ewma = alpha * squared + (1 - alpha) * ewma
        targets.append(ForwardHorizon(
            horizon=horizon, first_outcome_session=future[0].session_date,
            last_outcome_session=future[-1].session_date,
            label_end_at=future[-1].close_at, trailing_volatility=trailing,
            ewma_volatility=math.sqrt(ewma),
            garch_volatility=forecast_garch_11(returns, garch, horizon=horizon),
            gjr_volatility=forecast_gjr_garch_11(returns, gjr, horizon=horizon),
        ))
    return ForwardRiskRecord(
        symbol=symbol, origin_session=origin, source_snapshot_sha256=snapshot_sha,
        source_captured_at=source_captured_at, prediction_at=prediction_at,
        horizons=tuple(targets),
    )


def score_forward_risk_record(
    record: ForwardRiskRecord,
    later_prices: Sequence[HistoryPrice],
    *,
    label_snapshot_sha256: str,
    label_captured_at: datetime,
) -> tuple[ForwardRiskScore, ...]:
    """Score both horizons only after both labels close and a later snapshot arrives."""
    label_captured_at = _utc(label_captured_at, "label_captured_at")
    if label_captured_at <= record.prediction_at or any(
        label_captured_at < item.label_end_at for item in record.horizons
    ):
        raise ValueError("future risk label is not yet mature")
    label_sha = _digest(label_snapshot_sha256)
    if label_sha == record.source_snapshot_sha256:
        raise ValueError("label needs a later immutable snapshot")
    rows = _prices(later_prices)
    by_date = {row.session_date: row.adjusted_close for row in rows}
    if record.origin_session not in by_date:
        raise ValueError("label snapshot lacks the origin session")
    scores = []
    for target in record.horizons:
        expected = _outcome_sessions(record.origin_session, target.horizon)
        if (expected[0].session_date, expected[-1].session_date, expected[-1].close_at) != (
            target.first_outcome_session, target.last_outcome_session, target.label_end_at
        ):
            raise ValueError("forward record calendar differs from reviewed sessions")
        if any(day.session_date not in by_date for day in expected):
            raise ValueError("label snapshot lacks a target session")
        values = [by_date[record.origin_session],
                  *(by_date[session.session_date] for session in expected)]
        realized = math.sqrt(math.fsum(
            math.log(next_value / previous) ** 2
            for previous, next_value in zip(values, values[1:], strict=False)
        ) / target.horizon)
        scores.append(ForwardRiskScore(
            symbol=record.symbol, origin_session=record.origin_session,
            horizon=target.horizon, prediction_at=record.prediction_at,
            label_end_at=target.label_end_at, label_captured_at=label_captured_at,
            source_snapshot_sha256=record.source_snapshot_sha256,
            label_snapshot_sha256=label_sha, realized_volatility=realized,
            trailing_absolute_error=abs(target.trailing_volatility - realized),
            ewma_absolute_error=abs(target.ewma_volatility - realized),
            garch_absolute_error=abs(target.garch_volatility - realized),
            gjr_absolute_error=abs(target.gjr_volatility - realized),
        ))
    return tuple(scores)

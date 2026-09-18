from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


class ContractViolation(ValueError):
    """Raised when a source payload violates a required data contract."""


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    ticker: str
    event_ticker: str
    status: str
    observed_probability: float
    yes_bid: float | None
    yes_ask: float | None
    volume: float
    open_interest: float
    result: str | None
    observed_at: datetime
    raw_payload_hash: str
    source: str = "kalshi"


@dataclass(frozen=True, slots=True)
class ProbabilityCandle:
    end_period: datetime
    close_probability: float
    volume: float
    open_interest: float


def payload_sha256(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _decimal(value: Any, field: str, *, required: bool = False) -> Decimal | None:
    if value in (None, ""):
        if required:
            raise ContractViolation(f"{field} is required")
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ContractViolation(f"{field} must be numeric") from error
    if not parsed.is_finite():
        raise ContractViolation(f"{field} must be finite")
    return parsed


def _probability(value: Decimal, field: str) -> Decimal:
    if not Decimal("0") <= value <= Decimal("1"):
        raise ContractViolation(f"{field} must be in [0, 1]")
    return value


def market_probability(market: Mapping[str, Any]) -> float:
    bid = _decimal(market.get("yes_bid_dollars"), "yes_bid_dollars")
    ask = _decimal(market.get("yes_ask_dollars"), "yes_ask_dollars")

    if bid is not None:
        _probability(bid, "yes_bid_dollars")
    if ask is not None:
        _probability(ask, "yes_ask_dollars")
    if bid is not None and ask is not None:
        if bid > ask:
            raise ContractViolation("yes bid exceeds yes ask")
        return float((bid + ask) / Decimal("2"))

    last = _decimal(market.get("last_price_dollars"), "last_price_dollars", required=True)
    assert last is not None
    return float(_probability(last, "last_price_dollars"))


def _parse_timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise ContractViolation(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractViolation(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _markets(payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    events = payload.get("events")
    if not isinstance(events, list):
        raise ContractViolation("events must be a list")
    for event in events:
        if not isinstance(event, Mapping):
            raise ContractViolation("event must be an object")
        markets = event.get("markets")
        if not isinstance(markets, list):
            raise ContractViolation("event markets must be a list")
        for market in markets:
            if not isinstance(market, Mapping):
                raise ContractViolation("market must be an object")
            yield market


def iter_market_snapshots(
    payload: Mapping[str, Any],
    *,
    observed_at: datetime | None = None,
) -> Iterable[MarketSnapshot]:
    collected_at = observed_at or datetime.now(UTC)
    if collected_at.tzinfo is None or collected_at.utcoffset() is None:
        raise ContractViolation("observed_at must include a timezone")
    collected_at = collected_at.astimezone(UTC)

    for market in _markets(payload):
        ticker = market.get("ticker")
        event_ticker = market.get("event_ticker")
        if not isinstance(ticker, str) or not ticker:
            raise ContractViolation("ticker is required")
        if not isinstance(event_ticker, str) or not event_ticker:
            raise ContractViolation("event_ticker is required")

        result_value = market.get("result") or None
        if result_value not in (None, "yes", "no"):
            raise ContractViolation("result must be yes, no, or empty")

        bid = _decimal(market.get("yes_bid_dollars"), "yes_bid_dollars")
        ask = _decimal(market.get("yes_ask_dollars"), "yes_ask_dollars")
        volume = _decimal(market.get("volume_fp", "0"), "volume_fp", required=True)
        open_interest = _decimal(
            market.get("open_interest_fp", "0"),
            "open_interest_fp",
            required=True,
        )
        assert volume is not None and open_interest is not None
        if volume < 0 or open_interest < 0:
            raise ContractViolation("volume and open interest must be non-negative")

        yield MarketSnapshot(
            ticker=ticker,
            event_ticker=event_ticker,
            status=str(market.get("status", "")),
            observed_probability=market_probability(market),
            yes_bid=float(bid) if bid is not None else None,
            yes_ask=float(ask) if ask is not None else None,
            volume=float(volume),
            open_interest=float(open_interest),
            result=result_value,
            observed_at=collected_at,
            raw_payload_hash=payload_sha256(market),
        )


def _candle_close(candle: Mapping[str, Any]) -> Decimal:
    price = candle.get("price")
    if not isinstance(price, Mapping):
        raise ContractViolation("candle price must be an object")
    value = price.get("close_dollars", price.get("close"))
    parsed = _decimal(value, "price.close", required=True)
    assert parsed is not None
    return _probability(parsed, "price.close")


def validate_candlesticks(payload: Mapping[str, Any]) -> tuple[ProbabilityCandle, ...]:
    raw_candles = payload.get("candlesticks")
    if not isinstance(raw_candles, list):
        raise ContractViolation("candlesticks must be a list")

    candles: list[ProbabilityCandle] = []
    previous_timestamp: int | None = None
    for raw in raw_candles:
        if not isinstance(raw, Mapping):
            raise ContractViolation("candlestick must be an object")
        timestamp = raw.get("end_period_ts")
        if not isinstance(timestamp, int):
            raise ContractViolation("end_period_ts must be an integer")
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            raise ContractViolation("candlesticks must be strictly chronological")
        previous_timestamp = timestamp

        volume = _decimal(raw.get("volume_fp", raw.get("volume", "0")), "volume", required=True)
        open_interest = _decimal(
            raw.get("open_interest_fp", raw.get("open_interest", "0")),
            "open_interest",
            required=True,
        )
        assert volume is not None and open_interest is not None
        candles.append(
            ProbabilityCandle(
                end_period=datetime.fromtimestamp(timestamp, tz=UTC),
                close_probability=float(_candle_close(raw)),
                volume=float(volume),
                open_interest=float(open_interest),
            )
        )
    return tuple(candles)


from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from datetime import time as datetime_time
from typing import Any, Literal, Self, cast
from zoneinfo import ZoneInfo

import httpx
from shockgraph_data_pipeline.raw_store import ImmutableRawStore, RawArtifact

from shockgraph_collector.client import RETRYABLE_STATUS_CODES, RetryPolicy

ALPACA_DATA_BASE_URL = "https://data.alpaca.markets"
STOCK_BARS_PATH = "/v2/stocks/bars"
SUPPORTED_ASSETS = frozenset({"SPY", "TLT", "GLD"})
SUPPORTED_FEEDS = frozenset({"iex", "sip"})
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
NEW_YORK = ZoneInfo("America/New_York")


@dataclass(frozen=True, slots=True)
class AlpacaBarsPage:
    payload: dict[str, Any]
    artifact: RawArtifact


@dataclass(frozen=True, slots=True)
class AlpacaMinuteBar:
    asset_id: Literal["SPY", "TLT", "GLD"]
    source_start_at: datetime
    price_at: datetime
    available_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    extended_hours: bool
    raw_hash: str


def _utc_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Alpaca bar timestamp must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Alpaca bar timestamp must be ISO-8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("Alpaca bar timestamp must be UTC")
    if parsed.second or parsed.microsecond:
        raise ValueError("Alpaca one-minute bar must be minute-aligned")
    return parsed.astimezone(UTC)


def _finite_number(row: dict[str, Any], key: str, *, positive: bool = False) -> float:
    value = row.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"Alpaca bar {key} must be numeric")
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0):
        raise ValueError(f"Alpaca bar {key} is outside its valid range")
    return number


def _is_extended_hours(source_start_at: datetime) -> bool:
    local_time = source_start_at.astimezone(NEW_YORK).time().replace(tzinfo=None)
    return local_time < datetime_time(9, 30) or local_time >= datetime_time(16)


def normalize_alpaca_minute_bars(
    payload: dict[str, Any],
    *,
    raw_hash: str,
) -> tuple[AlpacaMinuteBar, ...]:
    if not HASH_PATTERN.fullmatch(raw_hash):
        raise ValueError("raw hash must be a SHA-256 hex digest")
    bars_by_symbol = payload.get("bars")
    if not isinstance(bars_by_symbol, dict):
        raise ValueError("Alpaca response bars must be an object")
    normalized: list[AlpacaMinuteBar] = []
    for symbol, rows in bars_by_symbol.items():
        if symbol not in SUPPORTED_ASSETS:
            raise ValueError("unsupported Alpaca symbol")
        if not isinstance(rows, list):
            raise ValueError("Alpaca symbol bars must be a list")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Alpaca bar row must be an object")
            source_start_at = _utc_datetime(row.get("t"))
            open_price = _finite_number(row, "o", positive=True)
            high = _finite_number(row, "h", positive=True)
            low = _finite_number(row, "l", positive=True)
            close = _finite_number(row, "c", positive=True)
            volume = _finite_number(row, "v")
            if volume < 0:
                raise ValueError("Alpaca bar volume is outside its valid range")
            if high < max(open_price, close, low) or low > min(open_price, close, high):
                raise ValueError("Alpaca bar OHLC bounds are inconsistent")
            close_at = source_start_at + timedelta(minutes=1)
            normalized.append(
                AlpacaMinuteBar(
                    asset_id=cast(Literal["SPY", "TLT", "GLD"], symbol),
                    source_start_at=source_start_at,
                    price_at=close_at,
                    available_at=close_at,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                    extended_hours=_is_extended_hours(source_start_at),
                    raw_hash=raw_hash,
                )
            )
    keys = {(bar.asset_id, bar.source_start_at) for bar in normalized}
    if len(keys) != len(normalized):
        raise ValueError("duplicate Alpaca minute bar")
    return tuple(sorted(normalized, key=lambda row: (row.price_at, row.asset_id)))


def _utc_iso(value: datetime, name: str) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class AlpacaMarketDataClient:
    def __init__(
        self,
        *,
        api_key_id: str,
        api_secret_key: str,
        timeout_seconds: float = 30,
        transport: httpx.BaseTransport | None = None,
        retry_policy: RetryPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if not api_key_id.strip() or not api_secret_key.strip():
            raise ValueError("Alpaca market data credentials are required")
        self.retry_policy = retry_policy or RetryPolicy()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.sleep = sleep or time.sleep
        self._client = httpx.Client(
            base_url=ALPACA_DATA_BASE_URL,
            timeout=timeout_seconds,
            transport=transport,
            follow_redirects=False,
            headers={
                "APCA-API-KEY-ID": api_key_id,
                "APCA-API-SECRET-KEY": api_secret_key,
                "User-Agent": "shockgraph-ai-research/0.1",
            },
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _get_json(self, params: dict[str, Any]) -> dict[str, Any]:
        delay = self.retry_policy.initial_backoff_seconds
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            response = self._client.get(STOCK_BARS_PATH, params=params)
            if response.status_code not in RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("Alpaca response must be a JSON object")
                return payload
            if attempt == self.retry_policy.max_attempts:
                response.raise_for_status()
            self.sleep(delay)
            delay *= self.retry_policy.multiplier
        raise RuntimeError("unreachable retry state")

    def collect_stock_bars(
        self,
        store: ImmutableRawStore,
        *,
        symbols: tuple[str, ...],
        start: datetime,
        end: datetime,
        feed: str = "sip",
        max_pages: int = 100,
    ) -> tuple[AlpacaBarsPage, ...]:
        unique_symbols = tuple(dict.fromkeys(symbols))
        if not unique_symbols or any(symbol not in SUPPORTED_ASSETS for symbol in unique_symbols):
            raise ValueError("symbols must contain only SPY, TLT, or GLD")
        if feed not in SUPPORTED_FEEDS:
            raise ValueError("feed must be iex or sip")
        start_iso = _utc_iso(start, "start")
        end_iso = _utc_iso(end, "end")
        if start >= end:
            raise ValueError("start must be before end")
        if feed == "sip" and end > self.clock() - timedelta(minutes=15):
            raise ValueError("historical SIP end must be at least 15 minutes old")
        if max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        base_params: dict[str, Any] = {
            "symbols": ",".join(unique_symbols),
            "timeframe": "1Min",
            "start": start_iso,
            "end": end_iso,
            "limit": 10000,
            "adjustment": "raw",
            "feed": feed,
            "sort": "asc",
        }
        pages: list[AlpacaBarsPage] = []
        page_token: str | None = None
        seen_tokens: set[str] = set()
        for _ in range(max_pages):
            params = dict(base_params)
            if page_token is not None:
                params["page_token"] = page_token
            payload = self._get_json(params)
            if not isinstance(payload.get("bars"), dict):
                raise ValueError("Alpaca response bars must be an object")
            artifact = store.save(
                payload,
                source="alpaca_market_data",
                endpoint=STOCK_BARS_PATH,
                request_params=params,
                observed_at=self.clock(),
            )
            pages.append(AlpacaBarsPage(payload=payload, artifact=artifact))
            next_token = payload.get("next_page_token")
            if next_token is None or next_token == "":
                return tuple(pages)
            if not isinstance(next_token, str):
                raise ValueError("Alpaca next page token must be a string or null")
            if next_token in seen_tokens:
                raise ValueError("Alpaca page token repeated")
            seen_tokens.add(next_token)
            page_token = next_token
        raise RuntimeError(f"Alpaca pagination exceeded max_pages={max_pages}")

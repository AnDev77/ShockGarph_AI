"""Archive Alpaca SIP daily bars and join raw/adjusted snapshots without backdating."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Self
from zoneinfo import ZoneInfo

import httpx
from shockgraph_data_pipeline.market_calendar import nasdaq_sessions
from shockgraph_data_pipeline.raw_store import ImmutableRawStore, RawArtifact

ALPACA_URL = "https://data.alpaca.markets"
_EASTERN = ZoneInfo("America/New_York")
_MAX_BYTES = 8_000_000
_MAX_PAGES = 20


@dataclass(frozen=True, slots=True)
class AlpacaPriceCapture:
    symbol: str
    captured_at: datetime
    csv_bytes: bytes
    raw_artifacts: tuple[RawArtifact, ...]
    raw_response_hashes: tuple[str, ...]
    session_count: int


def _number(value: object, name: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError(f"Alpaca {name} is missing or invalid")
    try:
        number = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"Alpaca {name} is invalid") from error
    if not number.is_finite() or number < 0 or (name == "close" and number == 0):
        raise ValueError(f"Alpaca {name} must be finite and nonnegative")
    return number


def _decode(body: bytes, sessions: dict[date, datetime]
            ) -> tuple[dict[date, tuple[Decimal, Decimal]], str | None]:
    try:
        data = json.loads(body)
        bars = data["bars"]
        token = data["next_page_token"]
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("Alpaca daily response is invalid JSON") from error
    if not isinstance(bars, list) or (token is not None and (not isinstance(token, str)
                                                             or not token)):
        raise ValueError("Alpaca daily response has invalid bars or cursor")
    parsed: dict[date, tuple[Decimal, Decimal]] = {}
    for bar in bars:
        if not isinstance(bar, dict):
            raise ValueError("Alpaca daily bar is invalid")
        try:
            stamped = datetime.fromisoformat(bar["t"].replace("Z", "+00:00"))
            if stamped.utcoffset() != UTC.utcoffset(None):
                raise ValueError("daily bar timestamp must be UTC")
            local = stamped.astimezone(_EASTERN)
            day = local.date()
            if local.time() != time.min or day not in sessions or day in parsed:
                raise ValueError("Alpaca bar is outside the scheduled session or duplicated")
            parsed[day] = _number(bar["c"], "close"), _number(bar["v"], "volume")
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError("Alpaca daily bar is incomplete") from error
    return parsed, token


class AlpacaDailyCollector:
    def __init__(self, key_id: str, secret_key: str, *,
                 transport: httpx.BaseTransport | None = None,
                 clock: Callable[[], datetime] | None = None) -> None:
        if not key_id or not secret_key:
            raise ValueError("Alpaca API credentials are missing")
        self.clock = clock or (lambda: datetime.now(UTC))
        self._client = httpx.Client(base_url=ALPACA_URL, transport=transport, timeout=25.0,
                                    follow_redirects=False, headers={
                                        "APCA-API-KEY-ID": key_id,
                                        "APCA-API-SECRET-KEY": secret_key,
                                    })

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self._client.close()

    def collect(self, symbol: str, start: date, end: date,
                store: ImmutableRawStore) -> AlpacaPriceCapture:
        if symbol not in ("TLT", "SPY"):
            raise ValueError("initial Alpaca collector supports TLT and SPY")
        sessions = {row.session_date: row.close_at for row in nasdaq_sessions(start, end)}
        if not sessions:
            raise ValueError("Alpaca request needs scheduled sessions")
        versions: dict[str, dict[date, tuple[Decimal, Decimal]]] = {}
        artifacts: list[RawArtifact] = []
        hashes: list[str] = []
        captures: list[datetime] = []
        for adjustment in ("raw", "all"):
            rows: dict[date, tuple[Decimal, Decimal]] = {}
            cursor: str | None = None
            seen_cursors: set[str] = set()
            for _ in range(_MAX_PAGES):
                params = {"timeframe": "1Day", "start": start.isoformat(),
                          "end": end.isoformat(), "adjustment": adjustment,
                          "feed": "sip", "limit": "10000"}
                if cursor is not None:
                    params["page_token"] = cursor
                response = self._client.get(f"/v2/stocks/{symbol}/bars", params=params)
                if response.status_code != 200:
                    raise ValueError(f"Alpaca daily bars returned HTTP {response.status_code}")
                body = response.content
                captured_at = self.clock()
                if captured_at.tzinfo is None or captured_at.utcoffset() != UTC.utcoffset(None):
                    raise ValueError("Alpaca capture clock must return UTC")
                if end >= captured_at.astimezone(_EASTERN).date():
                    raise ValueError("Alpaca SIP daily request must end before the US capture date")
                if len(body) > _MAX_BYTES or "json" not in response.headers.get(
                    "content-type", ""
                ).lower():
                    raise ValueError("Alpaca response is not bounded JSON")
                page, next_cursor = _decode(body, sessions)
                if any(day in rows for day in page):
                    raise ValueError("duplicate Alpaca bar across pages")
                if next_cursor in seen_cursors or (next_cursor and not page):
                    raise ValueError("Alpaca pagination did not advance")
                digest = hashlib.sha256(body).hexdigest()
                artifact = store.save(
                    {"format": "application/json", "body_base64": base64.b64encode(body).decode(),
                     "file_sha256": digest}, source="alpaca",
                    endpoint=f"/v2/stocks/{symbol}/bars", request_params=params,
                    observed_at=captured_at,
                )
                artifacts.append(artifact)
                hashes.append(digest)
                captures.append(captured_at)
                rows.update(page)
                if not next_cursor:
                    break
                seen_cursors.add(next_cursor)
                cursor = next_cursor
            else:
                raise ValueError("Alpaca daily bars exceeded the pagination limit")
            versions[adjustment] = rows
        if set(versions["raw"]) != set(sessions) or set(versions["all"]) != set(sessions):
            raise ValueError("Alpaca SIP raw and adjusted bars must cover all reviewed sessions")
        latest = max(captures)
        result = io.StringIO(newline="")
        writer = csv.writer(result, lineterminator="\n")
        writer.writerow(("session_date", "observed_at", "available_at", "close",
                         "adjusted_close", "volume"))
        for day, close_at in sessions.items():
            raw_close, volume = versions["raw"][day]
            adjusted_close, _ = versions["all"][day]
            writer.writerow((day.isoformat(), close_at.isoformat(), latest.isoformat(),
                             raw_close, adjusted_close, volume))
        return AlpacaPriceCapture(symbol, latest, result.getvalue().encode("utf-8"),
                                  tuple(artifacts), tuple(hashes), len(sessions))

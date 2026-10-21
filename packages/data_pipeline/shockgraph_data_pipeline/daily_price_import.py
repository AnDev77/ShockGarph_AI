from __future__ import annotations

import base64
import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from shockgraph_domain.records import AssetPriceRecord

from shockgraph_data_pipeline.market_calendar import (
    NASDAQ_CALENDAR_SOURCE,
    NASDAQ_CALENDAR_VERSION,
    nasdaq_sessions,
)
from shockgraph_data_pipeline.raw_store import ImmutableRawStore, RawArtifact

_COLUMNS = frozenset(
    ("session_date", "observed_at", "available_at", "close", "adjusted_close", "volume")
)


@dataclass(frozen=True, slots=True)
class DailyPriceQuality:
    source: str
    symbol: str
    venue: str
    mode: str
    captured_at: str
    calendar_source: str
    calendar_version: str
    file_sha256: str
    raw_payload_hash: str
    raw_created: bool
    price_count: int
    expected_session_count: int
    missing_sessions: tuple[str, ...]
    unexpected_sessions: tuple[str, ...]
    duplicate_sessions: tuple[str, ...]
    off_close_sessions: tuple[str, ...]
    late_sessions: tuple[str, ...]
    structurally_ready: bool
    rights_review_required: bool = True
    price_vintage_review_required: bool = True
    public_performance_allowed: bool = False


@dataclass(frozen=True, slots=True)
class DailyPriceImport:
    captured_at: datetime
    prices: tuple[AssetPriceRecord, ...]
    expected_sessions: tuple[date, ...]
    prediction_times: dict[date, datetime]
    raw_artifact: RawArtifact
    quality: DailyPriceQuality


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value.astimezone(UTC)


def _timestamp(value: str, column: str, line: int) -> datetime:
    try:
        return _utc(datetime.fromisoformat(value), column)
    except ValueError as error:
        raise ValueError(f"line {line}: {column} needs an ISO 8601 UTC timestamp") from error


def _decimal(value: str, column: str, line: int) -> Decimal:
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"line {line}: invalid {column}") from error
    if not number.is_finite():
        raise ValueError(f"line {line}: {column} must be finite")
    return number


def import_daily_prices(
    csv_bytes: bytes,
    *,
    store: ImmutableRawStore,
    source: str,
    captured_at: datetime,
    start: date,
    end: date,
    prediction_delay: timedelta = timedelta(hours=1),
    symbol: str = "TLT",
    full_snapshot: bool = False,
) -> DailyPriceImport:
    """Preserve the supplied file and check timestamps against the reviewed Nasdaq schedule.

    The caller is responsible for verifying the provider's rights and historical price vintages.
    This import does not produce a public performance claim or infer publication times.
    """
    captured_at = _utc(captured_at, "captured_at")
    if not source or not symbol or symbol != "TLT":
        raise ValueError("the initial import supports a named source and TLT only")
    if not timedelta(0) < prediction_delay <= timedelta(days=1):
        raise ValueError("prediction_delay must be positive and at most one day")
    sessions = nasdaq_sessions(start, end)
    if not sessions:
        raise ValueError("the calendar range has no scheduled sessions")
    prediction_times = {
        session.session_date: session.close_at + prediction_delay for session in sessions
    }
    closes = {session.session_date: session.close_at for session in sessions}
    file_hash = hashlib.sha256(csv_bytes).hexdigest()
    # Base64 preserves the exact input bytes, including BOMs and line endings, in the existing
    # content-addressed immutable JSON store. No provider data is committed to the repository.
    artifact = store.save(
        {
            "format": "text/csv; charset=utf-8",
            "file_sha256": file_hash,
            "content_base64": base64.b64encode(csv_bytes).decode("ascii"),
        },
        source=source,
        endpoint="/local/daily-adjusted-csv",
        observed_at=captured_at,
        request_params={"symbol": symbol, "venue": "XNAS"},
    )

    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("price CSV must be UTF-8") from error
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    if (
        reader.fieldnames is None
        or len(reader.fieldnames) != len(_COLUMNS)
        or (set(reader.fieldnames) != _COLUMNS)
    ):
        raise ValueError("price CSV needs exactly the documented six columns")
    prices = []
    counts: dict[date, int] = {}
    try:
        for line, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"line {line}: malformed price CSV row")
            try:
                session_date = date.fromisoformat(row["session_date"])
            except ValueError as error:
                raise ValueError(f"line {line}: invalid session_date") from error
            observed_at = _timestamp(row["observed_at"], "observed_at", line)
            available_at = _timestamp(row["available_at"], "available_at", line)
            if available_at > captured_at:
                raise ValueError(f"line {line}: available_at follows the captured file")
            volume = row["volume"]
            prices.append(
                AssetPriceRecord(
                    source=source,
                    symbol=symbol,
                    venue="XNAS",
                    session_date=session_date,
                    observed_at=observed_at,
                    available_at=available_at,
                    currency="USD",
                    close=_decimal(row["close"], "close", line),
                    adjusted_close=_decimal(row["adjusted_close"], "adjusted_close", line),
                    volume=_decimal(volume, "volume", line) if volume else None,
                    raw_payload_hash=artifact.payload_sha256,
                )
            )
            counts[session_date] = counts.get(session_date, 0) + 1
    except csv.Error as error:
        raise ValueError("malformed price CSV") from error

    actual = set(counts)
    expected = set(closes)
    missing = tuple(sorted(expected - actual))
    unexpected = tuple(sorted(actual - expected))
    duplicates = tuple(sorted(day for day, count in counts.items() if count > 1))
    off_close = tuple(
        sorted(
            {
                row.session_date
                for row in prices
                if row.session_date in closes and row.observed_at != closes[row.session_date]
            }
        )
    )
    late = tuple(
        sorted(
            {
                row.session_date
                for row in prices
                if row.session_date in prediction_times
                and row.available_at > prediction_times[row.session_date]
            }
        )
    )
    # Historical revised prices can be late relative to their original session but still
    # usable at a later archived capture. The snapshot evaluator gates on captured_at.
    ready = not (missing or unexpected or duplicates or off_close or (late and not full_snapshot))
    quality = DailyPriceQuality(
        source=source,
        symbol=symbol,
        venue="XNAS",
        mode="full_snapshot" if full_snapshot else "single_series",
        captured_at=captured_at.isoformat(),
        calendar_source=NASDAQ_CALENDAR_SOURCE,
        calendar_version=NASDAQ_CALENDAR_VERSION,
        file_sha256=file_hash,
        raw_payload_hash=artifact.payload_sha256,
        raw_created=artifact.created,
        price_count=len(prices),
        expected_session_count=len(sessions),
        missing_sessions=tuple(day.isoformat() for day in missing),
        unexpected_sessions=tuple(day.isoformat() for day in unexpected),
        duplicate_sessions=tuple(day.isoformat() for day in duplicates),
        off_close_sessions=tuple(day.isoformat() for day in off_close),
        late_sessions=tuple(day.isoformat() for day in late),
        structurally_ready=ready,
    )
    return DailyPriceImport(
        captured_at=captured_at,
        prices=tuple(prices),
        expected_sessions=tuple(session.session_date for session in sessions),
        prediction_times=prediction_times,
        raw_artifact=artifact,
        quality=quality,
    )

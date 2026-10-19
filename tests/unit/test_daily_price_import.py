from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from shockgraph_data_pipeline.daily_price_import import DailyPriceImport, import_daily_prices
from shockgraph_data_pipeline.market_calendar import nasdaq_2026_sessions
from shockgraph_data_pipeline.raw_store import ImmutableRawStore
from shockgraph_risk.daily import build_baseline_forecasts

CAPTURED = datetime(2026, 4, 7, 22, tzinfo=UTC)
START, END = date(2026, 3, 30), date(2026, 4, 7)
HEADER = "session_date,observed_at,available_at,close,adjusted_close,volume\n"


def price_csv(*, late: date | None = None, omit: date | None = None) -> bytes:
    lines = [HEADER]
    for index, session in enumerate(nasdaq_2026_sessions(START, END)):
        if session.session_date == omit:
            continue
        published = session.close_at + timedelta(minutes=5)
        if session.session_date == late:
            published += timedelta(hours=2)
        lines.append(
            f"{session.session_date},{session.close_at.isoformat()},"
            f"{published.isoformat()},{100 + index},{100 + index},1000\n"
        )
    return "".join(lines).encode()


def do_import(csv_bytes: bytes, tmp_path: Path) -> DailyPriceImport:
    return import_daily_prices(
        csv_bytes,
        store=ImmutableRawStore(tmp_path),
        source="licensed-test",
        captured_at=CAPTURED,
        start=START,
        end=END,
        prediction_delay=timedelta(minutes=10),
    )


def test_official_schedule_accounts_for_holidays_daylight_saving_and_early_close() -> None:
    sessions = nasdaq_2026_sessions(START, END)
    assert date(2026, 4, 3) not in [session.session_date for session in sessions]
    assert sessions[0].close_at == datetime(2026, 3, 30, 20, tzinfo=UTC)
    assert nasdaq_2026_sessions(date(2026, 1, 2), date(2026, 1, 2))[0].close_at == (
        datetime(2026, 1, 2, 21, tzinfo=UTC)
    )
    assert nasdaq_2026_sessions(date(2026, 11, 27), date(2026, 11, 27))[0].close_at == (
        datetime(2026, 11, 27, 18, tzinfo=UTC)
    )
    with pytest.raises(ValueError, match="only a valid 2026"):
        nasdaq_2026_sessions(date(2025, 12, 31), END)


def test_import_keeps_exact_bytes_and_connects_to_as_of_baseline(tmp_path: Path) -> None:
    raw = price_csv().replace(b"\n", b"\r\n")
    result = do_import(raw, tmp_path)
    assert result.quality.structurally_ready
    assert result.quality.file_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.quality.price_count == 6
    assert result.quality.rights_review_required
    assert result.quality.price_vintage_review_required
    assert not result.quality.public_performance_allowed
    assert all(price.raw_payload_hash == result.quality.raw_payload_hash for price in result.prices)
    payload = json.loads(result.raw_artifact.path.read_text(encoding="utf-8"))["payload"]
    assert payload["file_sha256"] == result.quality.file_sha256
    assert base64.b64decode(payload["content_base64"]) == raw
    forecasts = build_baseline_forecasts(
        result.prices, result.expected_sessions, result.prediction_times, horizon=2
    )
    assert len(forecasts) == 4
    assert forecasts[0].session_date == date(2026, 4, 1)

    repeat = do_import(raw, tmp_path)
    assert not repeat.raw_artifact.created
    assert repeat.raw_artifact.path == result.raw_artifact.path


def test_quality_reports_missing_duplicate_late_and_off_close_sessions(tmp_path: Path) -> None:
    missing = do_import(price_csv(omit=date(2026, 4, 2)), tmp_path)
    assert missing.quality.missing_sessions == ("2026-04-02",)
    assert not missing.quality.structurally_ready

    duplicated = price_csv() + price_csv().splitlines(keepends=True)[1]
    report = do_import(duplicated, tmp_path).quality
    assert report.duplicate_sessions == ("2026-03-30",)
    assert not report.structurally_ready

    report = do_import(price_csv(late=date(2026, 4, 1)), tmp_path).quality
    assert report.late_sessions == ("2026-04-01",)
    assert not report.structurally_ready

    off_close = price_csv().replace(b"2026-03-30T20:00:00+00:00", b"2026-03-30T19:00:00+00:00", 1)
    report = do_import(off_close, tmp_path).quality
    assert report.off_close_sessions == ("2026-03-30",)
    assert not report.structurally_ready

    holiday = price_csv() + b"2026-04-03,2026-04-03T20:00:00Z,2026-04-03T20:05:00Z,100,100,1\n"
    report = do_import(holiday, tmp_path).quality
    assert report.unexpected_sessions == ("2026-04-03",)
    assert not report.structurally_ready


def test_rejects_missing_vintage_or_future_price_and_bad_input(tmp_path: Path) -> None:
    raw = price_csv()
    with pytest.raises(ValueError, match="available_at needs an ISO 8601 UTC timestamp"):
        do_import(raw.replace(b"2026-03-30T20:05:00+00:00", b""), tmp_path)
    with pytest.raises(ValueError, match="follows the captured file"):
        do_import(raw.replace(b"2026-03-30T20:05:00+00:00", b"2026-04-08T20:05:00+00:00"), tmp_path)
    with pytest.raises(ValueError, match="six columns"):
        do_import(b"session_date,close\n2026-03-30,100\n", tmp_path)

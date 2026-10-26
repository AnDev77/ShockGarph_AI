from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from shockgraph_data_pipeline.market_calendar import nasdaq_sessions
from shockgraph_risk.exploratory_history import HistoryPrice
from shockgraph_risk.forward_risk_capture import (
    build_forward_risk_record,
    score_forward_risk_record,
)


def _history() -> tuple[HistoryPrice, ...]:
    sessions = nasdaq_sessions(date(2026, 1, 2), date(2026, 9, 30))[:140]
    current = 100.0
    rows = []
    for index, session in enumerate(sessions):
        current *= 1 + (0.008 if index % 4 else -0.012)
        rows.append(HistoryPrice(session.session_date, current))
    return tuple(rows)


def test_forward_forecast_is_fixed_before_future_close_and_score_waits_for_maturity() -> None:
    history = _history()
    origin = history[-1].session_date
    close = nasdaq_sessions(origin, origin)[0].close_at
    captured = close + timedelta(minutes=40)
    record = build_forward_risk_record(
        "SPY", history, source_snapshot_sha256="1" * 64,
        source_captured_at=captured, prediction_at=captured + timedelta(minutes=10),
    )
    assert record.public_performance_allowed is False
    assert record.origin_session == origin
    assert [item.horizon for item in record.horizons] == [5, 20]
    assert all(item.garch_volatility > 0 and item.gjr_volatility > 0
               for item in record.horizons)

    target_dates = [item.session_date for item in nasdaq_sessions(
        origin + timedelta(days=1), date(2026, 12, 31)
    )[:20]]
    label_prices = (*history, *(HistoryPrice(day, history[-1].adjusted_close *
                                            (1.01 ** (index + 1)))
                                for index, day in enumerate(target_dates)))
    mature = record.horizons[-1].label_end_at + timedelta(minutes=10)
    five_day = record.horizons[0].label_end_at + timedelta(minutes=10)
    with pytest.raises(ValueError, match="not yet mature"):
        score_forward_risk_record(record, label_prices, label_snapshot_sha256="2" * 64,
                                  label_captured_at=record.horizons[0].label_end_at -
                                  timedelta(minutes=1))
    first_five_prices = label_prices[:len(history) + 5]
    early = score_forward_risk_record(record, first_five_prices,
                                      label_snapshot_sha256="7" * 64,
                                      label_captured_at=five_day)
    assert [score.horizon for score in early] == [5]
    assert early[0].label_snapshot_sha256 == "7" * 64
    scores = score_forward_risk_record(
        record, label_prices, label_snapshot_sha256="2" * 64,
        label_captured_at=mature,
    )
    assert len(scores) == 2
    assert scores[0].realized_volatility > 0
    assert scores[0].source_snapshot_sha256 != scores[0].label_snapshot_sha256


def test_forward_record_rejects_late_or_unavailable_snapshot() -> None:
    history = _history()
    origin = history[-1].session_date
    next_close = nasdaq_sessions(origin + timedelta(days=1),
                                 date(2026, 12, 31))[0].close_at
    next_day = nasdaq_sessions(origin + timedelta(days=1),
                               date(2026, 12, 31))[0].session_date
    after_open = datetime.combine(next_day, time(10), ZoneInfo("America/New_York"))
    with pytest.raises(ValueError, match="next outcome open"):
        build_forward_risk_record("TLT", history, source_snapshot_sha256="3" * 64,
                                  source_captured_at=nasdaq_sessions(origin, origin)[0].close_at,
                                  prediction_at=after_open.astimezone(UTC))
    after_origin = nasdaq_sessions(origin, origin)[0].close_at + timedelta(minutes=10)
    with pytest.raises(ValueError, match="next outcome open"):
        build_forward_risk_record("TLT", history, source_snapshot_sha256="3" * 64,
                                  source_captured_at=after_origin, prediction_at=next_close)
    with pytest.raises(ValueError, match="capture"):
        build_forward_risk_record(
            "TLT", history, source_snapshot_sha256="3" * 64,
            source_captured_at=next_close,
            prediction_at=after_origin,
        )
    with pytest.raises(ValueError, match="UTC"):
        build_forward_risk_record(
            "TLT", history, source_snapshot_sha256="3" * 64,
            source_captured_at=datetime(2026, 8, 1), prediction_at=after_origin,
        )


def test_later_revision_changes_only_its_mature_label() -> None:
    prices = _history()
    origin = prices[-1].session_date
    captured = nasdaq_sessions(origin, origin)[0].close_at + timedelta(minutes=5)
    before = build_forward_risk_record(
        "TLT", prices, source_snapshot_sha256="4" * 64,
        source_captured_at=captured, prediction_at=captured + timedelta(minutes=1),
    )
    assert before.prediction_at.tzinfo == UTC
    targets = nasdaq_sessions(origin + timedelta(days=1), date(2026, 12, 31))[:20]
    later = (*prices, *(HistoryPrice(day.session_date, prices[-1].adjusted_close *
                                   (1.005 ** (index + 1)))
                       for index, day in enumerate(targets)))
    changed = (*later[:-1], HistoryPrice(targets[-1].session_date,
                                        later[-1].adjusted_close * 1.5))
    captured_later = targets[-1].close_at + timedelta(minutes=10)
    first = score_forward_risk_record(
        before, later, label_snapshot_sha256="5" * 64,
        label_captured_at=captured_later,
    )
    second = score_forward_risk_record(
        before, changed, label_snapshot_sha256="6" * 64,
        label_captured_at=captured_later,
    )
    assert first[0].realized_volatility == second[0].realized_volatility
    assert first[1].realized_volatility != second[1].realized_volatility
    assert first[1].source_snapshot_sha256 == second[1].source_snapshot_sha256

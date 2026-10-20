from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest
from shockgraph_data_pipeline.market_calendar import nasdaq_2026_sessions
from shockgraph_domain.records import AssetPriceRecord
from shockgraph_risk.daily import (
    PriceSnapshot,
    build_snapshot_forecasts,
    label_snapshot_forecasts,
    score_baselines,
)
from shockgraph_risk.macro_panel import MarketIndicatorObservation, build_macro_risk_panel
from shockgraph_risk.traditional_model import evaluate_traditional_holdout


def archive_and_panel(length: int = 75, *, missing: set[int] | None = None):
    sessions = nasdaq_2026_sessions(date(2026, 1, 5), date(2026, 6, 30))[:length]
    days = tuple(session.session_date for session in sessions)
    times = {session.session_date: session.close_at + timedelta(minutes=10)
             for session in sessions}
    values = [Decimal("100")]
    for index in range(1, length):
        values.append(values[-1] * (Decimal("1.015") if index % 7 else Decimal("0.965")))
    snapshots = []
    for end in range(length):
        rows = tuple(AssetPriceRecord(
            source="synthetic", symbol="TLT", venue="XNAS", currency="USD",
            session_date=session.session_date, observed_at=session.close_at,
            available_at=session.close_at + timedelta(minutes=2),
            close=values[index], adjusted_close=values[index],
            raw_payload_hash=f"{end + 1:064x}",
        ) for index, session in enumerate(sessions[:end + 1]))
        snapshots.append(PriceSnapshot(sessions[end].close_at + timedelta(minutes=5), rows))
    indicators = tuple(MarketIndicatorObservation(
        "DGS10", "synthetic", session.close_at,
        session.close_at + timedelta(minutes=3), 3 + index / 100, f"{index + 1:064x}",
    ) for index, session in enumerate(sessions) if index not in (missing or set()))
    forecasts = build_snapshot_forecasts(snapshots, days, times, horizon=5)
    panel = build_macro_risk_panel(
        forecasts, indicators, [], [], required_indicators=("DGS10",),
        max_indicator_age=timedelta(hours=2), max_probability_age=timedelta(days=1),
        max_release_lead=timedelta(days=1), include_probability_research=False,
    )
    return tuple(snapshots), days, times, panel


def evaluate(snapshots, days, times, panel, *, min_training: int = 20):
    return evaluate_traditional_holdout(
        panel, snapshots, days, times,
        holdout_start=times[days[40]], evaluation_at=times[days[-1]],
        indicator_names=("DGS10",), min_training=min_training,
        bootstrap_repeats=100,
    )


def test_ab_compares_same_dates_and_only_training_vintage_before_holdout() -> None:
    snapshots, days, times, panel = archive_and_panel(missing={44})
    report = evaluate(snapshots, days, times, panel)
    assert report.status == "evaluated_research_only"
    assert report.public_performance_allowed is False
    assert report.baseline_labeled_holdout_count == 30
    assert report.matched_holdout_count == 29
    assert report.nonoverlapping_window_count == 5
    assert report.last_training_label_at is not None
    assert report.last_training_label_at < times[days[40]]
    assert report.training_label_snapshot_hash == snapshots[40].prices[0].raw_payload_hash
    assert report.evaluation_label_snapshot_hash == snapshots[-1].prices[0].raw_payload_hash
    assert len(report.coefficients or ()) == 4  # intercept, two price inputs, one yield
    assert report.traditional_minus_ewma_mae_ci is not None

    labels = label_snapshot_forecasts(panel.baseline_rows, snapshots, days,
                                      evaluation_at=times[days[-1]])
    matched_days = {row.forecast.session_date for row in panel.traditional_rows}
    same_dates = [row for row in labels if row.forecast.session_date in matched_days]
    a = score_baselines(same_dates, holdout_start=times[days[40]], bootstrap_repeats=100)
    assert report.trailing_mae == pytest.approx(a.trailing_mae)
    assert report.ewma_mae == pytest.approx(a.ewma_mae)
    assert report.trailing_qlike == pytest.approx(a.trailing_qlike)


def test_after_holdout_revision_does_not_refit_training_coefficients() -> None:
    snapshots, days, times, panel = archive_and_panel()
    original = evaluate(snapshots, days, times, panel)
    final = snapshots[-1]
    revised_rows = tuple(row.model_copy(update={
        "adjusted_close": Decimal("70") if index == len(final.prices) - 1
        else row.adjusted_close,
        "raw_payload_hash": "f" * 64,
    })
                         for index, row in enumerate(final.prices))
    revised = snapshots[:-1] + (PriceSnapshot(final.captured_at, revised_rows),)
    forecasts = build_snapshot_forecasts(revised, days, times, horizon=5)
    market = [indicator for row in panel.traditional_rows for indicator in row.indicators]
    updated_panel = build_macro_risk_panel(
        forecasts, market, [], [], required_indicators=("DGS10",),
        max_indicator_age=timedelta(hours=2), max_probability_age=timedelta(days=1),
        max_release_lead=timedelta(days=1), include_probability_research=False,
    )
    changed = evaluate(revised, days, times, updated_panel)
    assert changed.coefficients == original.coefficients
    assert changed.training_input_sha256 == original.training_input_sha256
    assert changed.training_label_snapshot_hash == original.training_label_snapshot_hash
    assert changed.traditional_mae != original.traditional_mae
    assert changed.evaluation_label_snapshot_hash != original.evaluation_label_snapshot_hash


def test_insufficient_training_blocks_scores_and_future_indicator_is_rejected() -> None:
    snapshots, days, times, panel = archive_and_panel()
    blocked = evaluate(snapshots, days, times, panel, min_training=100)
    assert blocked.status == "blocked"
    assert blocked.reason == "insufficient_purged_training"
    assert blocked.traditional_mae is None
    assert blocked.ewma_mae is None
    assert blocked.coefficients is None

    first = panel.traditional_rows[0]
    future = replace(first.indicators[0],
                     observed_at=first.forecast.prediction_at + timedelta(minutes=1),
                     available_at=first.forecast.prediction_at + timedelta(minutes=2))
    invalid_panel = replace(panel, traditional_rows=(replace(first, indicators=(future,)),
                                                     *panel.traditional_rows[1:]))
    with pytest.raises(ValueError, match="future indicator"):
        evaluate(snapshots, days, times, invalid_panel)


def test_indicator_csv_requires_true_utc_availability_and_keeps_file_hash(tmp_path) -> None:
    from scripts.evaluate_traditional_holdout import load_indicators

    path = tmp_path / "indicators.csv"
    path.write_text("name,source,observed_at,available_at,value\n"
                    "DGS10,test,2026-01-05T21:00:00Z,2026-01-05T21:05:00Z,4.0\n")
    rows, digest = load_indicators(path)
    assert len(rows) == 1 and rows[0].raw_hash == digest
    path.write_text("name,source,observed_at,available_at,value\n"
                    "DGS10,test,2026-01-05T21:00:00,2026-01-05T21:05:00Z,4.0\n")
    with pytest.raises(ValueError, match="UTC"):
        load_indicators(path)

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from shockgraph_data_pipeline.market_calendar import nasdaq_2026_sessions
from shockgraph_domain.records import AssetPriceRecord
from shockgraph_risk.daily import PriceSnapshot, evaluate_snapshot_holdout


def synthetic_archive(length: int = 95) -> tuple[
    tuple[PriceSnapshot, ...], tuple[date, ...], dict[date, datetime]
]:
    sessions = nasdaq_2026_sessions(date(2026, 1, 5), date(2026, 7, 31))[:length]
    days = tuple(session.session_date for session in sessions)
    times = {session.session_date: session.close_at + timedelta(minutes=10)
             for session in sessions}
    values = [Decimal("100")]
    for index in range(1, length):
        values.append(values[-1] * (Decimal("1.006") if index % 3 else Decimal("0.991")))

    snapshots = []
    for end in range(length):
        rows = tuple(
            AssetPriceRecord(
                source="synthetic",
                symbol="TLT",
                venue="XNAS",
                session_date=session.session_date,
                observed_at=session.close_at,
                available_at=session.close_at + timedelta(minutes=2),
                currency="USD",
                close=values[index],
                adjusted_close=values[index],
                raw_payload_hash=f"{end + 1:064x}",
            )
            for index, session in enumerate(sessions[: end + 1])
        )
        snapshots.append(PriceSnapshot(sessions[end].close_at + timedelta(minutes=5), rows))
    return tuple(snapshots), days, times


def test_five_and_twenty_day_scores_use_same_fixed_holdout_and_archived_inputs() -> None:
    snapshots, days, times = synthetic_archive()
    report = evaluate_snapshot_holdout(
        snapshots, days, times, holdout_start=times[days[35]],
        evaluation_at=times[days[-1]],
    )
    repeated = evaluate_snapshot_holdout(
        snapshots, days, times, holdout_start=times[days[35]],
        evaluation_at=times[days[-1]],
    )

    assert report == repeated
    assert report.public_performance_allowed is False
    five, twenty = report.horizons
    assert (five.status, twenty.status) == ("evaluated_research_only",) * 2
    assert (five.holdout_forecast_count, twenty.holdout_forecast_count) == (60, 60)
    assert (five.labeled_holdout_count, twenty.labeled_holdout_count) == (55, 40)
    assert (five.nonoverlapping_window_count, twenty.nonoverlapping_window_count) == (11, 2)
    assert five.metrics is not None and twenty.metrics is not None
    assert five.metrics.sample_size == 55 and twenty.metrics.sample_size == 40
    assert five.metrics.first_prediction_at == twenty.metrics.first_prediction_at
    assert five.metrics.trailing_mae >= 0 and twenty.metrics.ewma_mae >= 0
    assert five.metrics.paired_mae_ci is not None
    assert twenty.metrics.paired_mae_ci is not None
    assert len(five.forecast_input_sha256 or "") == 64
    assert five.label_snapshot_hash == snapshots[-1].prices[0].raw_payload_hash


def test_twenty_day_score_is_withheld_without_two_nonoverlapping_windows() -> None:
    snapshots, days, times = synthetic_archive(70)
    report = evaluate_snapshot_holdout(
        snapshots, days, times, holdout_start=times[days[35]],
        evaluation_at=times[days[-1]],
    )
    five, twenty = report.horizons
    assert five.status == "evaluated_research_only"
    assert twenty.status == "blocked"
    assert twenty.reason == "insufficient_nonoverlapping_windows"
    assert twenty.labeled_holdout_count == 15
    assert twenty.nonoverlapping_window_count == 0
    assert twenty.metrics is None


def test_missing_capture_reports_first_session_and_discloses_no_metric() -> None:
    snapshots, days, times = synthetic_archive(70)
    archive = snapshots[:40] + snapshots[41:]
    report = evaluate_snapshot_holdout(
        archive, days, times, holdout_start=times[days[35]],
        evaluation_at=times[days[-1]],
    )
    for horizon in report.horizons:
        assert horizon.status == "blocked"
        assert horizon.reason == "missing_complete_asof_snapshot"
        assert horizon.first_missing_session == days[40]
        assert horizon.metrics is None


def test_invalid_evaluation_time_and_holdout_origin_are_rejected() -> None:
    snapshots, days, times = synthetic_archive(21)
    with pytest.raises(ValueError, match="evaluation must follow"):
        evaluate_snapshot_holdout(
            snapshots, days, times, holdout_start=times[days[5]],
            evaluation_at=snapshots[-2].captured_at,
        )
    with pytest.raises(ValueError, match="holdout_start must be a prediction time"):
        evaluate_snapshot_holdout(
            snapshots, days, times,
            holdout_start=times[days[5]] + timedelta(minutes=1),
            evaluation_at=times[days[-1]],
        )

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from shockgraph_domain.records import AssetPriceRecord
from shockgraph_risk.daily import (
    PriceSnapshot,
    build_snapshot_forecasts,
    label_snapshot_forecasts,
    purged_training_rows,
)


def sample_snapshots(
    *, revise: bool = True
) -> tuple[tuple[PriceSnapshot, ...], tuple[date, ...], dict[date, datetime]]:
    days = (
        date(2026, 3, 30),
        date(2026, 3, 31),
        date(2026, 4, 1),
        date(2026, 4, 2),
        date(2026, 4, 6),
        date(2026, 4, 7),
    )
    captures = [
        datetime.combine(day, datetime.min.time(), tzinfo=UTC).replace(hour=20, minute=10)
        for day in days
    ]
    original = [
        Decimal("100"),
        Decimal("102"),
        Decimal("99"),
        Decimal("103"),
        Decimal("101"),
        Decimal("105"),
    ]
    snapshots = []
    for end in range(len(days)):
        values = original[: end + 1]
        if revise and end >= 4:
            values = [
                value * Decimal("0.8") if offset < 2 else value
                for offset, value in enumerate(values)
            ]
        rows = []
        for index, day in enumerate(days[: end + 1]):
            observed_at = captures[index] - timedelta(minutes=10)
            available_at = observed_at + timedelta(minutes=5)
            if revise and end >= 4 and index < 2:
                available_at = captures[4] - timedelta(minutes=1)
            rows.append(
                AssetPriceRecord(
                    source="synthetic",
                    symbol="TLT",
                    venue="XNAS",
                    session_date=day,
                    observed_at=observed_at,
                    available_at=available_at,
                    currency="USD",
                    close=original[index],
                    adjusted_close=values[index],
                    raw_payload_hash=f"{end + 1 + (100 if revise and end >= 4 else 0):064x}",
                )
            )
        snapshots.append(PriceSnapshot(captured_at=captures[end], prices=tuple(rows)))
    return tuple(snapshots), days, dict(zip(days, captures, strict=True))


def test_revised_history_changes_only_forecasts_after_its_capture() -> None:
    revised, sessions, times = sample_snapshots()
    original, _, _ = sample_snapshots(revise=False)
    before = build_snapshot_forecasts(revised, sessions, times, horizon=2)
    counterfactual = build_snapshot_forecasts(original, sessions, times, horizon=2)

    assert [row.session_date for row in before] == list(sessions[2:])
    assert before[0].trailing_volatility == counterfactual[0].trailing_volatility
    assert before[0].ewma_volatility == counterfactual[0].ewma_volatility
    assert before[0].input_fingerprint == counterfactual[0].input_fingerprint
    assert before[-1].ewma_volatility != counterfactual[-1].ewma_volatility
    assert before[-1].input_fingerprint != counterfactual[-1].input_fingerprint


def test_missing_snapshot_and_incomplete_history_fail_closed() -> None:
    snapshots, sessions, times = sample_snapshots()
    without_current = snapshots[:3] + snapshots[4:]
    with pytest.raises(ValueError, match="no complete price snapshot"):
        build_snapshot_forecasts(without_current, sessions, times, horizon=2)

    missing_history = snapshots[3].prices[:1] + snapshots[3].prices[2:]
    broken = (
        snapshots[:3]
        + (PriceSnapshot(captured_at=snapshots[3].captured_at, prices=missing_history),)
        + snapshots[4:]
    )
    with pytest.raises(ValueError, match="complete calendar prefix"):
        build_snapshot_forecasts(broken, sessions, times, horizon=2)

    collision = snapshots[:2] + (snapshots[1],) + snapshots[2:]
    with pytest.raises(ValueError, match="capture times must increase"):
        build_snapshot_forecasts(collision, sessions, times, horizon=2)

    regressed = (
        snapshots[:3]
        + (PriceSnapshot(captured_at=snapshots[3].captured_at, prices=snapshots[3].prices[:2]),)
        + snapshots[4:]
    )
    with pytest.raises(ValueError, match="cannot lose previously covered"):
        build_snapshot_forecasts(regressed, sessions, times, horizon=2)


def test_label_revision_cannot_enter_training_before_its_capture() -> None:
    snapshots, sessions, times = sample_snapshots()
    forecasts = build_snapshot_forecasts(snapshots, sessions, times, horizon=2)
    labeled = label_snapshot_forecasts(
        forecasts, snapshots, sessions, evaluation_at=snapshots[-1].captured_at
    )

    assert len(labeled) == 2
    assert labeled[0].label_available_at == snapshots[-1].captured_at
    assert labeled[0].label_snapshot_hash == snapshots[-1].prices[0].raw_payload_hash
    assert purged_training_rows(labeled, next_split_at=times[sessions[4]]) == ()
    assert (
        label_snapshot_forecasts(
            forecasts, snapshots, sessions, evaluation_at=snapshots[3].captured_at
        )
        == ()
    )

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from shockgraph_domain.records import AssetPriceRecord
from shockgraph_risk.daily import (
    build_baseline_forecasts,
    label_forecasts,
    purged_training_rows,
    score_baselines,
)


def sample_prices(
    returns: tuple[float, ...] = (0.1, -0.2, 0.3, -0.4, 0.2, -0.1),
) -> tuple[tuple[AssetPriceRecord, ...], tuple[date, ...], dict[date, datetime]]:
    sessions = tuple(date(2026, 1, 5) + timedelta(days=index) for index in range(len(returns) + 1))
    prices = []
    value = 100.0
    for index, session in enumerate(sessions):
        if index:
            value *= math.exp(returns[index - 1])
        observed_at = datetime.combine(session, datetime.min.time(), tzinfo=UTC).replace(hour=21)
        prices.append(
            AssetPriceRecord(
                source="synthetic-fixture",
                symbol="TLT",
                venue="XNAS",
                session_date=session,
                observed_at=observed_at,
                available_at=observed_at + timedelta(minutes=5),
                currency="USD",
                close=Decimal(str(value)),
                adjusted_close=Decimal(str(value)),
                raw_payload_hash=f"{index:064x}",
            )
        )
    predictions = {session: price.observed_at + timedelta(minutes=10)
                   for session, price in zip(sessions, prices, strict=True)}
    return tuple(prices), sessions, predictions


def available(price: AssetPriceRecord) -> datetime:
    assert price.available_at is not None
    return price.available_at


def adjusted(price: AssetPriceRecord) -> Decimal:
    assert price.adjusted_close is not None
    return price.adjusted_close


def test_trailing_and_ewma_use_only_known_past_returns() -> None:
    prices, sessions, times = sample_prices()
    forecasts = build_baseline_forecasts(prices, sessions, times, horizon=2)

    assert len(forecasts) == 5
    assert forecasts[0].trailing_volatility == pytest.approx(math.sqrt((0.1**2 + 0.2**2) / 2))
    assert forecasts[0].ewma_volatility == pytest.approx(forecasts[0].trailing_volatility)
    assert forecasts[1].ewma_volatility**2 == pytest.approx(
        (2 / 3) * 0.3**2 + (1 / 3) * forecasts[0].ewma_volatility**2
    )

    # Changing every future price must not change the forecast at the earlier snapshot.
    modified = list(prices)
    for index in range(3, len(modified)):
        modified[index] = modified[index].model_copy(
            update={"adjusted_close": adjusted(modified[index]) * Decimal("3")}
        )
    assert build_baseline_forecasts(modified, sessions, times, horizon=2)[0] == forecasts[0]


def test_labels_need_full_future_window_and_actual_availability() -> None:
    prices, sessions, times = sample_prices()
    forecasts = build_baseline_forecasts(prices, sessions, times, horizon=2)
    not_yet = available(prices[4]) - timedelta(seconds=1)

    assert label_forecasts(forecasts, prices, sessions, evaluation_at=not_yet) == ()
    labeled = label_forecasts(forecasts, prices, sessions, evaluation_at=available(prices[4]))
    assert len(labeled) == 1
    assert labeled[0].forecast.session_date == sessions[2]
    assert labeled[0].label_end_at == prices[4].observed_at
    assert labeled[0].label_available_at == available(prices[4])
    assert labeled[0].realized_volatility == pytest.approx(math.sqrt((0.3**2 + 0.4**2) / 2))


def test_twenty_day_label_starts_after_the_forecast_session() -> None:
    prices, sessions, times = sample_prices(returns=(0.01,) * 60)
    forecasts = build_baseline_forecasts(prices, sessions, times, horizon=20)

    assert forecasts[0].session_date == sessions[20]
    assert forecasts[0].trailing_volatility == pytest.approx(0.01)
    assert label_forecasts(
        forecasts, prices, sessions, evaluation_at=available(prices[40]) - timedelta(seconds=1)
    ) == ()
    labeled = label_forecasts(
        forecasts, prices, sessions, evaluation_at=available(prices[40])
    )
    assert len(labeled) == 1
    assert labeled[0].realized_volatility == pytest.approx(0.01)
    assert labeled[0].label_end_at == prices[40].observed_at


def test_late_price_version_and_missing_session_fail_closed() -> None:
    prices, sessions, times = sample_prices()
    late = list(prices)
    late[1] = late[1].model_copy(update={"available_at": times[sessions[2]] + timedelta(hours=1)})
    with pytest.raises(ValueError, match="unavailable at prediction_at"):
        build_baseline_forecasts(late, sessions, times, horizon=2)

    with pytest.raises(ValueError, match="expected session"):
        build_baseline_forecasts(prices[:3] + prices[4:], sessions, times, horizon=2)
    without_vintage = list(prices)
    without_vintage[1] = without_vintage[1].model_copy(update={"available_at": None})
    with pytest.raises(ValueError, match="exact available_at"):
        build_baseline_forecasts(without_vintage, sessions, times, horizon=2)


def test_purge_removes_training_labels_that_overlap_next_split() -> None:
    prices, sessions, times = sample_prices()
    forecasts = build_baseline_forecasts(prices, sessions, times, horizon=2)
    labeled = label_forecasts(forecasts, prices, sessions, evaluation_at=available(prices[-1]))

    training = purged_training_rows(labeled, next_split_at=times[sessions[4]])
    assert [row.forecast.session_date for row in training] == [sessions[2]]
    assert all(row.label_end_at < times[sessions[4]] for row in training)


def test_report_uses_paired_holdout_and_discloses_small_sample_uncertainty() -> None:
    prices, sessions, times = sample_prices()
    forecasts = build_baseline_forecasts(prices, sessions, times, horizon=2)
    labeled = label_forecasts(forecasts, prices, sessions, evaluation_at=available(prices[-1]))
    report = score_baselines(labeled, holdout_start=times[sessions[3]], bootstrap_repeats=100)

    assert report.sample_size == 2
    assert report.first_prediction_at == times[sessions[3]]
    assert report.trailing_mae >= 0
    assert report.ewma_mae >= 0
    assert report.ewma_minus_trailing_mae == pytest.approx(report.ewma_mae - report.trailing_mae)
    assert report.paired_mae_ci is None  # Fewer than two nonoverlapping two-day blocks.

    longer, days, predictions = sample_prices(returns=(0.05, -0.1, 0.02, -0.04) * 7)
    longer_forecasts = build_baseline_forecasts(longer, days, predictions, horizon=5)
    rows = label_forecasts(longer_forecasts, longer, days, evaluation_at=available(longer[-1]))
    first = score_baselines(rows, holdout_start=predictions[days[5]], bootstrap_repeats=100)
    second = score_baselines(rows, holdout_start=predictions[days[5]], bootstrap_repeats=100)
    assert first.sample_size == 19
    assert first.paired_mae_ci == second.paired_mae_ci
    assert first.paired_mae_ci is not None


def test_rejects_naive_prediction_clock_and_mixed_assets() -> None:
    prices, sessions, times = sample_prices()
    naive = dict(times)
    naive[sessions[2]] = naive[sessions[2]].replace(tzinfo=None)
    with pytest.raises(ValueError, match="UTC"):
        build_baseline_forecasts(prices, sessions, naive, horizon=2)
    mixed = list(prices)
    mixed[2] = mixed[2].model_copy(update={"symbol": "SPY"})
    with pytest.raises(ValueError, match="one asset"):
        build_baseline_forecasts(mixed, sessions, times, horizon=2)


def test_rejects_price_that_overflows_float_math() -> None:
    prices, sessions, times = sample_prices()
    invalid = list(prices)
    invalid[2] = invalid[2].model_copy(update={"adjusted_close": Decimal("1e10000")})
    with pytest.raises(ValueError, match="finite and positive"):
        build_baseline_forecasts(invalid, sessions, times, horizon=2)

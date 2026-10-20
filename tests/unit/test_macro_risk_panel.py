from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from shockgraph_analytics.contracts import ProbabilitySnapshot
from shockgraph_domain.records import AssetPriceRecord
from shockgraph_risk.daily import PriceSnapshot, VolatilityForecast, build_snapshot_forecasts
from shockgraph_risk.macro_panel import (
    MarketIndicatorObservation,
    ScheduledMacroEvent,
    build_macro_risk_panel,
)

DAY = timedelta(days=1)
HOUR = timedelta(hours=1)


def clock(day: int, hour: int = 21) -> datetime:
    return datetime(2026, 1, day, hour, tzinfo=UTC)


def baseline(day: int) -> VolatilityForecast:
    return VolatilityForecast("TLT", date(2026, 1, day), clock(day), 5, 0.02, 0.019, "a" * 64)


def indicator(name: str, day: int, *, value: float = 2.0) -> MarketIndicatorObservation:
    return MarketIndicatorObservation(name, "synthetic", clock(day, 20), clock(day, 20),
                                      value, "b" * 64)


def event(*, announced: datetime | None = None) -> ScheduledMacroEvent:
    published = announced or clock(4)
    return ScheduledMacroEvent("CPI-1", "CPI", "synthetic", "CPI-ABOVE-03", published, published,
                               clock(7, 14), "c" * 64)


def probability(day: int, *, available: datetime | None = None,
                value: float = 0.6, ticker: str = "CPI-ABOVE-03") -> ProbabilitySnapshot:
    return ProbabilitySnapshot(event_id="CPI-1", market_ticker=ticker,
                               observed_at=clock(day, 20),
                               available_at=available or clock(day, 20),
                               probability=value, raw_hash="d" * 64)


def panel(forecasts, indicators, events, probabilities, **limits):
    return build_macro_risk_panel(
        forecasts, indicators, events, probabilities,
        required_indicators=("US10Y", "VIX"),
        max_indicator_age=limits.get("max_indicator_age", DAY * 2),
        max_probability_age=limits.get("max_probability_age", DAY * 2),
        max_release_lead=limits.get("max_release_lead", DAY * 3),
    )


def test_a_b_c_share_prediction_rows_and_future_revisions_do_not_leak() -> None:
    forecasts = (baseline(5), baseline(6), baseline(7))
    market = [indicator(name, day, value=float(day))
              for day in (5, 6, 7) for name in ("US10Y", "VIX")]
    early = panel(forecasts, market, [event()], [probability(5), probability(6, value=0.8)])

    assert early.coverage.baseline_count == 3
    assert early.coverage.traditional_count == 3
    assert early.coverage.probability_count == 2
    assert early.coverage.unique_probability_events == 1  # Two days are one release.
    assert early.coverage.exclusions == (("no_known_upcoming_event", 1),)
    assert early.probability_rows[0].traditional is early.traditional_rows[0]
    assert early.probability_rows[0].traditional.forecast is early.baseline_rows[0]
    assert early.probability_rows[0].probability.probability == 0.6
    assert early.probability_rows[1].probability.probability == 0.8

    changed_later = [
        replace(row, value=999.0) if row.observed_at == clock(6, 20) else row
        for row in market
    ]
    revised = panel(forecasts, changed_later, [event()],
                    [probability(5), probability(6, value=0.1)])
    assert revised.probability_rows[0] == early.probability_rows[0]
    assert revised.probability_rows[1].probability.probability == 0.1


def test_unannounced_event_delayed_snapshot_and_wrong_contract_are_excluded() -> None:
    forecasts = (baseline(5), baseline(6))
    market = [indicator(name, day) for day in (5, 6) for name in ("US10Y", "VIX")]
    after_first = event(announced=clock(6, 18))
    late = probability(5, available=clock(6, 22))
    result = panel(forecasts, market, [after_first],
                   [late, probability(6, ticker="OTHER")])

    assert len(result.traditional_rows) == 2
    assert result.probability_rows == ()
    assert result.coverage.exclusions == (
        ("missing_probability", 1), ("no_known_upcoming_event", 1)
    )


def test_backfilled_observations_only_change_later_as_of_rows() -> None:
    forecasts = (baseline(5), baseline(6))
    market = [indicator(name, 5) for name in ("US10Y", "VIX")]
    updated_market = market + [
        MarketIndicatorObservation(name, "synthetic", clock(5, 20), clock(6, 20),
                                   99.0, "e" * 64) for name in ("US10Y", "VIX")
    ]
    original = panel(forecasts, market, [event()], [probability(5)])
    revised = panel(forecasts, updated_market, [event()], [
        probability(5), probability(5, available=clock(6, 20), value=0.9)
    ])

    assert original.probability_rows[0] == revised.probability_rows[0]
    assert revised.probability_rows[1].traditional.indicators[0].value == 99.0
    assert revised.probability_rows[1].probability.probability == 0.9


def test_nearest_known_release_is_not_skipped_for_a_later_event_with_data() -> None:
    nearer = ScheduledMacroEvent("FOMC-1", "FOMC", "synthetic", "FOMC-RATE",
                                 clock(4), clock(4), clock(7, 13), "e" * 64)
    market = [indicator(name, 5) for name in ("US10Y", "VIX")]
    result = panel([baseline(5)], market, [event(), nearer], [probability(5)])

    assert result.coverage.traditional_count == 1
    assert result.coverage.probability_count == 0
    assert result.coverage.exclusions == (("missing_probability", 1),)


def test_stale_and_missing_inputs_are_counted_without_zero_filling() -> None:
    forecasts = (baseline(5), baseline(6))
    market = [indicator("US10Y", 5), indicator("VIX", 5)]
    no_current_market = panel(forecasts, market, [event()], [probability(5)],
                              max_indicator_age=HOUR * 2)
    assert no_current_market.coverage.traditional_count == 1
    assert no_current_market.coverage.exclusions == (("stale_indicator", 1),)

    missing_market = panel(forecasts, market[:1], [event()], [probability(5)])
    assert missing_market.coverage.traditional_count == 0
    assert missing_market.coverage.exclusions == (("missing_indicator", 2),)

    stale_probability = panel(forecasts, market, [event()], [probability(5)],
                              max_probability_age=HOUR / 2)
    assert stale_probability.coverage.probability_count == 0
    assert stale_probability.coverage.exclusions == (("stale_probability", 2),)


def test_price_snapshot_baselines_connect_on_matching_sessions() -> None:
    days = (date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7),
            date(2026, 1, 8), date(2026, 1, 9), date(2026, 1, 12))
    captures = [datetime.combine(day, datetime.min.time(), tzinfo=UTC).replace(
        hour=21, minute=10) for day in days]
    snapshots = []
    for end in range(len(days)):
        rows = tuple(AssetPriceRecord(
            source="synthetic", symbol="TLT", venue="XNAS", session_date=day,
            observed_at=captures[i] - timedelta(minutes=10),
            available_at=captures[i] - timedelta(minutes=5),
            currency="USD", close=Decimal(str(100 + i)),
            adjusted_close=Decimal(str(100 + i)), raw_payload_hash=f"{end:064x}"
        ) for i, day in enumerate(days[:end + 1]))
        snapshots.append(PriceSnapshot(captures[end], rows))

    forecasts = build_snapshot_forecasts(snapshots, days,
                                         dict(zip(days, captures, strict=True)), horizon=2)
    market = [indicator(name, day) for day in (7, 8, 9, 12)
              for name in ("US10Y", "VIX")]
    release = ScheduledMacroEvent("CPI-1", "CPI", "synthetic", "CPI-ABOVE-03",
                                  clock(5), clock(5),
                                  clock(9, 14), "c" * 64)
    result = panel(forecasts, market, [release], [probability(7), probability(8)])

    assert tuple(row.traditional.forecast.session_date
                 for row in result.probability_rows) == days[2:4]
    assert all(row.traditional.forecast.input_fingerprint for row in result.probability_rows)
    assert result.coverage.baseline_count == 4
    assert result.coverage.traditional_count == 4
    assert result.coverage.probability_count == 2
    assert result.coverage.exclusions == (("no_known_upcoming_event", 2),)


def test_rejects_ambiguous_vintages_or_missing_price_lineage() -> None:
    market = [indicator("US10Y", 5), indicator("VIX", 5)]
    with pytest.raises(ValueError, match="fingerprint"):
        panel([replace(baseline(5), input_fingerprint=None)], market,
              [event()], [probability(5)])
    with pytest.raises(ValueError, match="duplicate indicator vintage"):
        panel([baseline(5)], market + market[:1], [event()], [probability(5)])
    with pytest.raises(ValueError, match="duplicate probability vintage"):
        panel([baseline(5)], market, [event()], [probability(5), probability(5)])
    with pytest.raises(ValueError, match="one fixed schedule"):
        panel([baseline(5)], market, [event(), event()], [probability(5)])
    with pytest.raises(ValueError, match="UTC"):
        MarketIndicatorObservation("US10Y", "synthetic", clock(5).replace(tzinfo=None),
                                   clock(5), 2.0, "b" * 64)

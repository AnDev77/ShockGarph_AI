from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Literal

import pytest
from pydantic import ValidationError
from shockgraph_analytics.paper_panel import (
    AssetMinuteBar,
    CpiReleaseVintage,
    assemble_event_asset_panel,
    build_asset_windows,
    event_reference_month,
    parse_bls_cpi_release,
)

RAW_HASH = "a" * 64
SAMPLE_RELEASE = """
<html><body>
Transmission of material in this release is embargoed until
8:30 a.m. (ET) Wednesday, March 11, 2026 USDL-26-0437
CONSUMER PRICE INDEX - FEBRUARY 2026
The Consumer Price Index for All Urban Consumers (CPI-U) increased 0.3 percent
on a seasonally adjusted basis in February, after rising 0.2 percent in January.
</body></html>
"""
LEGACY_RELEASE = """
<html><body>
Transmission of material in this release is embargoed until
8:30 a.m. (ET) November 10, 2021 USDL-21-1973
CONSUMER PRICE INDEX � OCTOBER 2021
The Consumer Price Index for All Urban Consumers (CPI-U) increased 0.9 percent
in October on a seasonally adjusted basis after rising 0.4 percent in September.
</body></html>
"""


def test_event_ticker_maps_to_reference_month() -> None:
    assert event_reference_month("CPI-21OCT") == date(2021, 10, 1)
    assert event_reference_month("KXCPI-26AUG") == date(2026, 8, 1)
    with pytest.raises(ValueError, match="CPI event ticker"):
        event_reference_month("KXFED-26AUG")


def test_bls_release_parser_preserves_first_value_and_utc_release_time() -> None:
    release = parse_bls_cpi_release(
        SAMPLE_RELEASE,
        event_ticker="KXCPI-26FEB",
        source_url="https://www.bls.gov/news.release/archives/cpi_03112026.htm",
        raw_hash=RAW_HASH,
    )
    assert release.reference_month == date(2026, 2, 1)
    assert release.release_at == datetime(2026, 3, 11, 12, 30, tzinfo=UTC)
    assert release.actual_mom_first == pytest.approx(0.3)
    assert release.outcome == "no"


def test_bls_release_parser_rejects_wrong_event_month() -> None:
    with pytest.raises(ValueError, match="reference month"):
        parse_bls_cpi_release(
            SAMPLE_RELEASE,
            event_ticker="KXCPI-26JAN",
            source_url="https://www.bls.gov/news.release/archives/cpi_03112026.htm",
            raw_hash=RAW_HASH,
        )


def test_bls_release_parser_accepts_legacy_heading_and_embargo_format() -> None:
    release = parse_bls_cpi_release(
        LEGACY_RELEASE,
        event_ticker="CPI-21OCT",
        source_url="https://www.bls.gov/news.release/archives/cpi_11102021.htm",
        raw_hash=RAW_HASH,
    )
    assert release.release_at == datetime(2021, 11, 10, 13, 30, tzinfo=UTC)
    assert release.actual_mom_first == pytest.approx(0.9)
    assert release.outcome == "yes"


def test_bls_release_parser_rejects_two_month_shutdown_change() -> None:
    html = SAMPLE_RELEASE.replace(
        "increased 0.3 percent\non a seasonally adjusted basis in February",
        "increased 0.2 percent on a seasonally adjusted basis over the 2 months "
        "from December 2025 to February",
    )
    with pytest.raises(ValueError, match="one-month"):
        parse_bls_cpi_release(
            html,
            event_ticker="KXCPI-26FEB",
            source_url="https://www.bls.gov/news.release/archives/cpi_03112026.htm",
            raw_hash=RAW_HASH,
        )


def _release() -> CpiReleaseVintage:
    return CpiReleaseVintage(
        event_id="cpi-2026-02",
        event_ticker="KXCPI-26FEB",
        reference_month=date(2026, 2, 1),
        release_at=datetime(2026, 3, 11, 12, 30, tzinfo=UTC),
        actual_mom_first=0.3,
        threshold=0.3,
        outcome="no",
        source_url="https://www.bls.gov/news.release/archives/cpi_03112026.htm",
        raw_hash=RAW_HASH,
    )


def _bar(asset: Literal["SPY", "TLT", "GLD"], minute: int, close: float) -> AssetMinuteBar:
    observed = datetime(2026, 3, 11, 12, 30, tzinfo=UTC) + timedelta(minutes=minute)
    return AssetMinuteBar(
        asset_id=asset,
        price_at=observed,
        available_at=observed + timedelta(seconds=2),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=10,
        extended_hours=True,
        raw_hash=RAW_HASH,
    )


def test_asset_window_requires_exact_bars_and_reports_missing_asset() -> None:
    bars = [
        _bar("SPY", -1, 100),
        _bar("SPY", 5, 101),
        _bar("TLT", -1, 100),
        _bar("TLT", 5, 99),
        _bar("GLD", -1, 100),
    ]
    result = build_asset_windows([_release()], bars, horizons={"m5": timedelta(minutes=5)})

    assert len(result.windows) == 2
    assert result.windows[0].return_value == pytest.approx(0.01)
    assert result.windows[1].return_value == pytest.approx(-0.01)
    assert result.coverage == (
        {
            "event_id": "cpi-2026-02",
            "asset_id": "GLD",
            "horizon": "m5",
            "status": "missing_end_bar",
        },
    )
    assert result.common_event_ids == ()


def test_asset_bar_rejects_inconsistent_ohlc() -> None:
    with pytest.raises(ValidationError, match="OHLC"):
        AssetMinuteBar(
            asset_id="SPY",
            price_at=datetime(2026, 3, 11, 12, 29, tzinfo=UTC),
            available_at=datetime(2026, 3, 11, 12, 29, 2, tzinfo=UTC),
            open=100,
            high=99,
            low=98,
            close=100,
            volume=10,
            extended_hours=True,
            raw_hash=RAW_HASH,
        )


def test_balanced_panel_joins_only_pre_release_probability_and_all_assets() -> None:
    bars = [
        _bar("SPY", -1, 100),
        _bar("SPY", 5, 101),
        _bar("TLT", -1, 100),
        _bar("TLT", 5, 99),
        _bar("GLD", -1, 100),
        _bar("GLD", 5, 100.5),
    ]
    windows = build_asset_windows([_release()], bars, horizons={"m5": timedelta(minutes=5)})
    probabilities = [
        {
            "event_ticker": "KXCPI-26FEB",
            "market_ticker": "KXCPI-26FEB-T0.3",
            "status": "eligible",
            "quote_end_at": "2026-03-11T12:29:00+00:00",
            "probability_yes": "0.7",
            "spread": "0.04",
        }
    ]

    panel = assemble_event_asset_panel(probabilities, [_release()], windows)

    assert len(panel.rows) == 3
    assert panel.common_event_ids == ("cpi-2026-02",)
    assert panel.rows[0].probability_yes == pytest.approx(0.7)
    assert {row.asset_id for row in panel.rows} == {"SPY", "TLT", "GLD"}


def test_balanced_panel_rejects_probability_observed_after_release() -> None:
    bars = [_bar(asset, minute, 100) for asset in ("SPY", "TLT", "GLD") for minute in (-1, 5)]
    windows = build_asset_windows([_release()], bars, horizons={"m5": timedelta(minutes=5)})
    probabilities = [
        {
            "event_ticker": "KXCPI-26FEB",
            "market_ticker": "KXCPI-26FEB-T0.3",
            "status": "eligible",
            "quote_end_at": "2026-03-11T12:31:00+00:00",
            "probability_yes": "0.7",
            "spread": "0.04",
        }
    ]

    with pytest.raises(ValueError, match="before release"):
        assemble_event_asset_panel(probabilities, [_release()], windows)

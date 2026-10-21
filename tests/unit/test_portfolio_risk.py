from __future__ import annotations

import hashlib
import math
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from shockgraph_domain.portfolio import validate_positions
from shockgraph_domain.records import AssetPriceRecord
from shockgraph_risk.portfolio import (
    build_portfolio_forecasts,
    label_portfolio_forecasts,
    purged_portfolio_training_rows,
    score_portfolio_baselines,
)


def sample_panel(
    spy_returns: tuple[float, ...], tlt_returns: tuple[float, ...]
) -> tuple[dict[str, tuple[AssetPriceRecord, ...]], tuple[date, ...], dict[date, datetime]]:
    assert len(spy_returns) == len(tlt_returns)
    sessions = tuple(date(2026, 1, 5) + timedelta(days=i) for i in range(len(spy_returns) + 1))
    times = {s: datetime(s.year, s.month, s.day, 21, 10, tzinfo=UTC) for s in sessions}
    panel = {}
    for symbol, returns in (("SPY", spy_returns), ("TLT", tlt_returns)):
        value = 100.0
        rows = []
        for index, session in enumerate(sessions):
            if index:
                value *= 1 + returns[index - 1]
            observed_at = datetime(session.year, session.month, session.day, 21, tzinfo=UTC)
            rows.append(
                AssetPriceRecord(
                    source="synthetic-fixture",
                    symbol=symbol,
                    venue="XNAS",
                    observed_at=observed_at,
                    available_at=observed_at + timedelta(minutes=5),
                    session_date=session,
                    currency="USD",
                    close=Decimal(str(value)),
                    adjusted_close=Decimal(str(value)),
                    raw_payload_hash=hashlib.sha256(
                        f"{symbol}:{session.isoformat()}:{value}".encode()
                    ).hexdigest(),
                )
            )
        panel[symbol] = tuple(rows)
    return panel, sessions, times


def equal_weights():
    return validate_positions([{"symbol": "SPY", "weight": 0.5}, {"symbol": "TLT", "weight": 0.5}])


def doubled_price(row: AssetPriceRecord) -> AssetPriceRecord:
    assert row.adjusted_close is not None
    return row.model_copy(update={"adjusted_close": row.adjusted_close * Decimal("2")})


def test_joint_returns_capture_offsetting_assets_and_correlation_change() -> None:
    spy = (0.1, -0.1, 0.1, -0.1)
    opposite, sessions, times = sample_panel(spy, (-0.1, 0.1, -0.1, 0.1))
    offset = build_portfolio_forecasts(opposite, sessions, times, equal_weights(), horizon=2)
    assert offset[0].trailing_volatility == pytest.approx(0, abs=1e-14)

    switching, sessions, times = sample_panel(spy, (-0.1, 0.1, 0.1, -0.1))
    forecasts = build_portfolio_forecasts(switching, sessions, times, equal_weights(), horizon=2)
    assert forecasts[0].ewma_volatility == pytest.approx(0, abs=1e-14)
    assert forecasts[-1].ewma_volatility > 0.04
    assert forecasts[-1].trailing_volatility > 0.09


def test_future_prices_never_change_an_earlier_portfolio_forecast() -> None:
    panel, sessions, times = sample_panel((0.02, -0.03, 0.01, 0.05), (0.01, 0.02, -0.02, -0.01))
    first = build_portfolio_forecasts(panel, sessions, times, equal_weights(), horizon=2)[0]
    modified = dict(panel)
    modified["SPY"] = panel["SPY"][:3] + tuple(doubled_price(row) for row in panel["SPY"][3:])
    earlier = build_portfolio_forecasts(modified, sessions, times, equal_weights(), horizon=2)[0]
    assert earlier == first


def test_missing_session_late_price_and_mixed_currency_fail_closed() -> None:
    panel, sessions, times = sample_panel((0.02, 0.03, -0.01), (0.01, -0.02, 0.02))
    missing = dict(panel)
    missing["TLT"] = panel["TLT"][:2] + panel["TLT"][3:]
    with pytest.raises(ValueError, match="every expected session"):
        build_portfolio_forecasts(missing, sessions, times, equal_weights(), horizon=2)

    late = dict(panel)
    late["TLT"] = panel["TLT"][:2] + (
        panel["TLT"][2].model_copy(
            update={"available_at": times[sessions[2]] + timedelta(minutes=1)}
        ),
    ) + panel["TLT"][3:]
    with pytest.raises(ValueError, match="unavailable at prediction_at"):
        build_portfolio_forecasts(late, sessions, times, equal_weights(), horizon=2)

    mixed = dict(panel)
    mixed["TLT"] = tuple(row.model_copy(update={"currency": "KRW"}) for row in panel["TLT"])
    with pytest.raises(ValueError, match="requires all prices in USD"):
        build_portfolio_forecasts(mixed, sessions, times, equal_weights(), horizon=2)


def test_portfolio_label_waits_for_all_constituents_and_purges_overlap() -> None:
    spy = (0.03, -0.02, 0.05, -0.04, 0.01, 0.02, -0.01)
    tlt = (0.01, 0.02, -0.03, 0.02, -0.02, 0.01, 0.01)
    panel, sessions, times = sample_panel(spy, tlt)
    forecasts = build_portfolio_forecasts(panel, sessions, times, equal_weights(), horizon=2)
    first_label_time = panel["TLT"][4].available_at
    assert first_label_time is not None
    assert label_portfolio_forecasts(
        forecasts, panel, sessions, equal_weights(),
        evaluation_at=first_label_time - timedelta(seconds=1),
    ) == ()
    late_constituent = dict(panel)
    late_constituent["TLT"] = panel["TLT"][:4] + (
        panel["TLT"][4].model_copy(
            update={"available_at": first_label_time + timedelta(hours=1)}
        ),
    ) + panel["TLT"][5:]
    assert label_portfolio_forecasts(
        forecasts, late_constituent, sessions, equal_weights(), evaluation_at=first_label_time
    ) == ()
    labeled = label_portfolio_forecasts(
        forecasts, panel, sessions, equal_weights(), evaluation_at=first_label_time
    )
    assert len(labeled) == 1
    realized = (math.log1p((spy[2] + tlt[2]) / 2) ** 2
                + math.log1p((spy[3] + tlt[3]) / 2) ** 2) / 2
    assert labeled[0].realized_volatility == pytest.approx(math.sqrt(realized))

    last_available = panel["TLT"][-1].available_at
    assert last_available is not None
    all_labeled = label_portfolio_forecasts(
        forecasts, panel, sessions, equal_weights(), evaluation_at=last_available
    )
    assert [row.forecast.session_date for row in purged_portfolio_training_rows(
        all_labeled, next_split_at=times[sessions[4]]
    )] == [sessions[2]]
    report = score_portfolio_baselines(
        all_labeled, holdout_start=times[sessions[3]], bootstrap_repeats=100
    )
    assert report.positions == equal_weights().positions
    assert report.metrics.sample_size == 3
    assert report.metrics.paired_mae_ci is None

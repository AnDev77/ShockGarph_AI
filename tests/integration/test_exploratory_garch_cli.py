from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from scripts.plot_exploratory_garch import compare_private_history


def test_private_garch_report_uses_same_dates_as_existing_ridge(tmp_path: Path) -> None:
    rows = ["session_date,adjusted_close"]
    day = date(2024, 1, 2)
    price = 100.0
    days = []
    while len(days) < 260:
        if day.weekday() < 5:
            price *= 1.012 if len(days) % 7 else 0.97
            days.append(day)
            rows.append(f"{day},{price}")
        day += timedelta(days=1)
    source = tmp_path / "research.csv"
    source.write_text("\n".join(rows) + "\n", encoding="utf-8")

    report, horizons = compare_private_history(
        source, source="synthetic-test", holdout_start=days[150]
    )
    assert report["historical_price_vintages_verified"] is False
    assert report["independent_model_selection_holdout"] is False
    assert report["public_performance_allowed"] is False
    assert len(report["source_file_sha256"]) == 64
    for row, entry in zip(horizons, report["horizons"], strict=True):
        ridge = entry["price_only_ridge"]
        assert row.sample_size == ridge["holdout_count"]
        assert row.first_prediction_date == ridge["first_holdout_date"]
        assert row.ewma_mae == ridge["ewma_mae"]

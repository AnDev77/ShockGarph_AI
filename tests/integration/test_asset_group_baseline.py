from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_cpi_asset_groups import evaluate_groups  # noqa: E402


def _csv(path: Path, rows: list[dict[str, object]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_group_evaluation_preserves_independent_samples_and_threshold(tmp_path: Path) -> None:
    releases = []
    probabilities = []
    bars = []
    for index in range(1, 17):
        year = 2024 + (index - 1) // 12
        month = (index - 1) % 12 + 1
        event_id = f"cpi-{year}-{month:02d}"
        ticker = f"KXCPI-{year % 100:02d}{date(year, month, 1):%b}".upper()
        next_year = year + (month == 12)
        next_month = month % 12 + 1
        release_day = f"{next_year}-{next_month:02d}-12"
        releases.append(
            {
                "event_id": event_id,
                "event_ticker": ticker,
                "reference_month": f"{year}-{month:02d}-01",
                "release_at": f"{release_day}T13:30:00+00:00",
                "actual_mom_first": 0.4,
                "threshold": 0.3,
                "bls_outcome": "yes",
                "source_url": (
                    "https://www.bls.gov/news.release/archives/"
                    f"cpi_{next_month:02d}12{next_year}.htm"
                ),
                "raw_hash": "a" * 64,
            }
        )
        probabilities.append(
            {"event_ticker": ticker, "status": "stale" if index == 16 else "eligible"}
        )
        for asset in ("SPY", "TLT", "GLD"):
            if asset == "GLD" and index > 6:
                continue
            for minute, price in ((29, 100), (35, 101), ("00", 102)):
                timestamp = (
                    f"{release_day}T13:{minute}:00+00:00"
                    if isinstance(minute, int)
                    else f"{release_day}T14:00:00+00:00"
                )
                bars.append(
                    {
                        "asset_id": asset,
                        "price_at": timestamp,
                        "available_at": timestamp,
                        "open": price,
                        "high": price,
                        "low": price,
                        "close": price,
                        "volume": 10,
                        "extended_hours": "true",
                        "raw_hash": "b" * 64,
                    }
                )
    release_path = _csv(tmp_path / "releases.csv", releases)
    probability_path = _csv(tmp_path / "probabilities.csv", probabilities)
    bar_path = _csv(tmp_path / "bars.csv", bars)
    output = tmp_path / "report.json"
    report = json.loads(
        evaluate_groups(release_path, probability_path, bar_path, output).read_text()
    )

    assert report["group_results"]["SPY:m5"]["eligible_events"] == 15
    assert report["group_results"]["SPY:m5"]["test_events"] == 10
    assert report["group_results"]["SPY:m5"]["status"] == "evaluated"
    assert report["group_results"]["GLD:m5"]["eligible_events"] == 6
    assert report["group_results"]["GLD:m5"]["metrics"] == {}
    assert report["primary_cohort"]["assets"] == ["SPY", "TLT"]
    assert report["primary_cohort"]["common_eligible_events"] == 15
    assert report["primary_cohort"]["research_status"] == "insufficient_research_events"
    assert report["primary_cohort"]["research_additional_events_needed"] == 15
    assert report["supplemental_asset"] == "GLD"
    assert "return_value" not in output.read_text()
    assert evaluate_groups(release_path, probability_path, bar_path, output) == output
    bars[0]["volume"] = 11
    _csv(bar_path, bars)
    with pytest.raises(ValueError, match="existing group report differs"):
        evaluate_groups(release_path, probability_path, bar_path, output)

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_cpi_asset_panel import build_panel_dataset  # noqa: E402
from evaluate_cpi_price_baseline import evaluate_panel  # noqa: E402


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_panel_export_creates_balanced_three_asset_dataset(tmp_path) -> None:
    releases = tmp_path / "releases.csv"
    probabilities = tmp_path / "probabilities.csv"
    bars = tmp_path / "bars.csv"
    _write_csv(
        releases,
        [
            {
                "event_id": "cpi-2026-02",
                "event_ticker": "KXCPI-26FEB",
                "reference_month": "2026-02-01",
                "release_at": "2026-03-11T12:30:00+00:00",
                "actual_mom_first": 0.3,
                "threshold": 0.3,
                "bls_outcome": "no",
                "source_url": "https://www.bls.gov/news.release/archives/cpi_03112026.htm",
                "raw_hash": "a" * 64,
            }
        ],
    )
    _write_csv(
        probabilities,
        [
            {
                "event_ticker": "KXCPI-26FEB",
                "market_ticker": "KXCPI-26FEB-T0.3",
                "outcome": "no",
                "status": "eligible",
                "quote_end_at": "2026-03-11T12:29:00+00:00",
                "probability_yes": 0.1,
                "spread": 0.02,
            }
        ],
    )
    bar_rows = []
    for asset, end_price in (("SPY", 101), ("TLT", 99), ("GLD", 100.5)):
        for timestamp, price in (
            ("2026-03-11T12:29:00+00:00", 100),
            ("2026-03-11T12:35:00+00:00", end_price),
            ("2026-03-11T13:00:00+00:00", end_price),
        ):
            bar_rows.append(
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
    _write_csv(bars, bar_rows)

    destination = build_panel_dataset(
        releases,
        probabilities,
        bars,
        tmp_path / "output",
    )

    metadata = json.loads(destination.joinpath("metadata.json").read_text(encoding="utf-8"))
    assert metadata["common_events"] == 1
    assert metadata["panel_rows"] == 6
    with destination.joinpath("event_asset_panel.csv").open(encoding="utf-8", newline="") as handle:
        panel_rows = list(csv.DictReader(handle))
    assert {row["asset_id"] for row in panel_rows} == {"SPY", "TLT", "GLD"}
    report_path = evaluate_panel(destination, tmp_path / "baseline")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "insufficient_test_events"
    assert report["metrics"] == {}
    assert evaluate_panel(destination, tmp_path / "baseline") == report_path
    destination.joinpath("event_asset_panel.csv").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        evaluate_panel(destination, tmp_path / "baseline")

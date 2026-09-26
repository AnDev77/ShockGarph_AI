from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_kalshi_cpi import score_event_probabilities  # noqa: E402
from export_paper_dataset import export_paper_dataset  # noqa: E402


def _report() -> dict[str, Any]:
    events: list[dict[str, Any]] = [
        {
            "event_ticker": f"KXCPI-{index}",
            "market_ticker": f"KXCPI-{index}-T0.3",
            "tier": "historical",
            "cutoff_at": f"2025-{index + 1:02d}-01T12:25:00+00:00",
            "outcome": "yes" if index % 2 == 0 else "no",
            "status": "no_eligible_candles",
            "candidate_candles": 0,
            "eligible_candles": 0,
            "near_release_candles": 0,
        }
        for index in range(10)
    ]
    events.extend(
        [
            {
                "event_ticker": "KXCPI-10",
                "market_ticker": "KXCPI-10-T0.3",
                "tier": "historical",
                "cutoff_at": "2025-11-01T12:25:00+00:00",
                "outcome": "yes",
                "status": "eligible",
                "candidate_candles": 2,
                "eligible_candles": 1,
                "near_release_candles": 1,
                "latest_eligible_end_at": "2025-11-01T12:24:00+00:00",
                "quote_end_at": "2025-11-01T12:24:00+00:00",
                "probability_yes": 0.8,
                "spread": 0.02,
                "volume": 4.0,
            },
            {
                "event_ticker": "KXCPI-11",
                "market_ticker": "KXCPI-11-T0.3",
                "tier": "recent",
                "cutoff_at": "2025-12-01T12:25:00+00:00",
                "outcome": "no",
                "status": "eligible",
                "candidate_candles": 2,
                "eligible_candles": 1,
                "near_release_candles": 1,
                "latest_eligible_end_at": "2025-12-01T12:24:00+00:00",
                "quote_end_at": "2025-12-01T12:24:00+00:00",
                "probability_yes": 0.2,
                "spread": 0.03,
                "volume": 3.0,
            },
        ]
    )
    return {
        "checked_at": "2026-09-26T00:00:00+00:00",
        "series_ticker": "KXCPI",
        "threshold_suffix": "-T0.3",
        "settled_fixed_threshold_events": len(events),
        "status_counts": {
            "eligible": 2,
            "stale": 0,
            "no_eligible_candles": 10,
            "access_error": 0,
        },
        "event_probability_comparison": score_event_probabilities(events),
        "events": events,
    }


def test_export_creates_stable_event_level_dataset_with_lineage(tmp_path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(_report(), sort_keys=True), encoding="utf-8")

    first = export_paper_dataset(report_path, tmp_path / "paper")
    second = export_paper_dataset(report_path, tmp_path / "paper")

    assert first == second
    metadata = json.loads(first.joinpath("metadata.json").read_text(encoding="utf-8"))
    assert metadata["source_report_sha256"] == hashlib.sha256(report_path.read_bytes()).hexdigest()
    assert metadata["event_count"] == 12
    assert metadata["schema_version"] == "paper-event-v1"
    with first.joinpath("event_coverage.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 12
    assert rows[10]["outcome_binary"] == "1"
    assert float(rows[10]["expanding_historical_probability"]) == pytest.approx(0.5)
    assert float(rows[10]["brier_loss_difference"]) == pytest.approx(0.04 - 0.25)
    assert rows[0]["probability_yes"] == ""


def test_export_rejects_comparison_for_unknown_market(tmp_path) -> None:
    report = _report()
    report["event_probability_comparison"]["comparisons"][0]["market_ticker"] = "UNKNOWN"
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown market"):
        export_paper_dataset(report_path, tmp_path / "paper")


def test_export_rejects_a_tampered_historical_baseline(tmp_path) -> None:
    report = _report()
    report["event_probability_comparison"]["comparisons"][0]["expanding_historical_probability"] = (
        0.9
    )
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="historical probability"):
        export_paper_dataset(report_path, tmp_path / "paper")

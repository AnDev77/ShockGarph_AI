from __future__ import annotations

import csv
import json

from analyze_event_coverage_losses import analyze_losses


def _write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_loss_diagnostic_separates_four_exclusion_stages(tmp_path) -> None:
    releases = _write_csv(
        tmp_path / "releases.csv",
        [
            {
                "event_id": f"event-{index}",
                "event_ticker": f"ticker-{index}",
                "reference_month": f"2026-0{index}-01",
            }
            for index in range(1, 5)
        ],
    )
    probabilities = _write_csv(
        tmp_path / "probabilities.csv",
        [
            {"event_ticker": "ticker-1", "status": "eligible"},
            {"event_ticker": "ticker-2", "status": "stale"},
            {"event_ticker": "ticker-3", "status": "eligible"},
            {"event_ticker": "ticker-4", "status": "no_eligible_candles"},
        ],
    )
    asset_coverage = _write_json(
        tmp_path / "coverage.json",
        {
            "coverage": [
                {
                    "event_id": "event-3",
                    "asset_id": "TLT",
                    "horizon": "m5",
                    "status": "missing_start_bar",
                },
                {
                    "event_id": "event-4",
                    "asset_id": "GLD",
                    "horizon": "m30",
                    "status": "missing_end_bar",
                },
            ]
        },
    )
    asset_metadata = _write_json(
        tmp_path / "asset.json",
        {"common_event_ids": ["event-1", "event-2"]},
    )
    panel_metadata = _write_json(
        tmp_path / "panel.json",
        {"common_event_ids": ["event-1"]},
    )

    output = analyze_losses(
        releases,
        probabilities,
        asset_coverage,
        asset_metadata,
        panel_metadata,
        tmp_path / "diagnostic.json",
        min_train=1,
        min_test=2,
    )
    result = json.loads(output.read_text(encoding="utf-8"))

    assert result["exclusion_stage_counts"] == {
        "included": 1,
        "price_only_loss": 1,
        "probability_and_price_loss": 1,
        "probability_only_loss": 1,
    }
    assert result["additional_model_common_events_needed"] == 2
    assert result["price_failure_asset_counts"] == {
        "GLD:missing_end_bar": 1,
        "TLT:missing_start_bar": 1,
    }
    assert "probability_yes" not in output.read_text(encoding="utf-8")

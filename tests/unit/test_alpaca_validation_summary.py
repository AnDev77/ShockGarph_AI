from __future__ import annotations

import json

import pytest
from export_alpaca_validation_summary import export_summary


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_summary_excludes_credentials_prices_and_event_predictions(tmp_path) -> None:
    asset = _write(
        tmp_path / "asset.json",
        {
            "schema_version": "alpaca-etf-minute-bars-v1",
            "source": "alpaca_market_data",
            "feed": "iex",
            "release_events": 53,
            "bar_rows": 101,
            "coverage_rows": 318,
            "coverage_status_counts": {"complete": 90, "missing_start_bar": 228},
            "common_events": 15,
            "bar_csv_sha256": "bars",
        },
    )
    panel = _write(
        tmp_path / "panel.json",
        {"schema_version": "cpi-event-asset-panel-v1", "panel_sha256": "panel"},
    )
    baseline = _write(
        tmp_path / "baseline.json",
        {
            "status": "evaluated",
            "method": "expanding_prior_event_mean_vs_zero_return",
            "input_panel_sha256": "panel",
            "train_start_events": 5,
            "test_events": 10,
            "required_test_events": 10,
            "metrics": {"SPY:m5": {"test_events": 10, "mae": 0.1, "zero_mae": 0.2}},
            "predictions": [{"actual_return": 0.25}],
            "api_key": "must-not-leak",
        },
    )

    output = export_summary(asset, panel, baseline, tmp_path / "summary.json")
    content = output.read_text(encoding="utf-8")

    assert "must-not-leak" not in content
    assert "actual_return" not in content
    assert json.loads(content)["evaluation"]["metrics"]["SPY:m5"]["mae"] == 0.1


def test_summary_rejects_mismatched_panel_hash(tmp_path) -> None:
    asset = _write(
        tmp_path / "asset.json",
        {
            "schema_version": "alpaca-etf-minute-bars-v1",
            "source": "alpaca_market_data",
            "feed": "iex",
            "release_events": 1,
            "bar_rows": 1,
            "coverage_rows": 1,
            "coverage_status_counts": {},
            "common_events": 0,
            "bar_csv_sha256": "bars",
        },
    )
    panel = _write(
        tmp_path / "panel.json",
        {"schema_version": "cpi-event-asset-panel-v1", "panel_sha256": "panel-a"},
    )
    baseline = _write(
        tmp_path / "baseline.json",
        {"input_panel_sha256": "panel-b"},
    )

    with pytest.raises(ValueError, match="checksums differ"):
        export_summary(asset, panel, baseline, tmp_path / "summary.json")

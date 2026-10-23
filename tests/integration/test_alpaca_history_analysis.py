from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import UTC, date, datetime

import pytest
from shockgraph_data_pipeline.market_calendar import nasdaq_sessions

from scripts.analyze_alpaca_history import run_analysis


def test_alpaca_analysis_uses_same_dates_and_rejects_changed_capture(tmp_path) -> None:
    base = tmp_path / "private"
    sessions = nasdaq_sessions(date(2024, 1, 2), date(2025, 3, 28))
    captured = datetime(2025, 4, 1, tzinfo=UTC).isoformat()
    prices = []
    for symbol in ("TLT", "SPY"):
        path = base / symbol / "capture.csv"
        path.parent.mkdir(parents=True)
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, lineterminator="\n")
            writer.writerow(("session_date", "observed_at", "available_at", "close",
                             "adjusted_close", "volume"))
            for index, session in enumerate(sessions):
                adjusted = 100 * math.exp(index * 0.0002 + 0.04 * math.sin(index / 9))
                writer.writerow((session.session_date, session.close_at.isoformat(), captured,
                                 adjusted * (1.02 if symbol == "TLT" else 1.01),
                                 adjusted, 1000))
        prices.append({"symbol": symbol, "feed": "sip", "capture": captured,
                       "snapshot_path": str(path), "session_count": len(sessions),
                       "normalized_csv_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest = base / "captures" / "capture.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"status": "archived_research_only", "prices": prices}),
                        encoding="utf-8")

    report = run_analysis(manifest, holdout_start=date(2025, 1, 2))
    assert report["status"] == "exploratory_current_history_only"
    assert report["public_product_performance_allowed"] is False
    assert report["historical_price_vintages_verified"] is False
    assert [item["symbol"] for item in report["assets"]] == ["TLT", "SPY"]
    assert [item["session_count"] for item in report["assets"]] == [len(sessions)] * 2
    first = report["assets"][0]["horizons"][0]
    second = report["assets"][1]["horizons"][0]
    assert first["first_prediction_date"] == second["first_prediction_date"]
    assert first["holdout_prediction_dates"] == second["holdout_prediction_dates"]
    assert first["last_training_label_date"] < first["first_prediction_date"]
    for asset in report["assets"]:
        assert (asset["pre_holdout_price_sessions"] + asset["holdout_price_sessions"]
                == len(sessions))
        for horizon in asset["horizons"]:
            count = horizon["holdout_prediction_dates"]
            length = horizon["horizon_sessions"]
            assert horizon["future_tail_not_scored"] == length
            assert asset["holdout_price_sessions"] - length == count
            assert horizon["nonoverlapping_windows"] == (count + length - 1) // length
            assert horizon["conservative_full_start_blocks"] == count // length
            monthly_refit = horizon["monthly_refit"]
            if horizon["baseline_status"] == "exploratory_current_history_only":
                assert monthly_refit["status"] == "exploratory_current_history_only"
                assert monthly_refit["sample_size"] == count
                assert monthly_refit["refit_month_count"] > 0
                assert monthly_refit["first_refit_training_returns"] >= 100
                assert monthly_refit["mae_daily_volatility_percentage_points"]["gjr"]
                assert monthly_refit["paired_block_ci_difference_percentage_points"][
                    "gjr_vs_static_gjr"
                ] is not None
            else:
                assert monthly_refit["mae_daily_volatility_percentage_points"]["gjr"] is None
            months = horizon["monthly_error_diagnostics"]
            if months is not None:
                rows = months["months"]
                assert sum(row["prediction_dates"] for row in rows) == count
                assert len(rows) == months["month_count"]
                assert months["gjr_better_month_count"] == sum(
                    row["gjr_minus_garch_mae_percentage_points"] < -0.000001
                    for row in rows
                )
                assert rows[0]["month"] < rows[-1]["month"]
                assert sum(row["prediction_dates"] *
                           row["gjr_minus_garch_mae_percentage_points"]
                           for row in rows) / count == pytest.approx(
                    horizon["mae_daily_volatility_percentage_points"]["gjr"]
                    - horizon["mae_daily_volatility_percentage_points"]["garch"],
                    abs=0.0002,
                )
            diagnostics = horizon["overlap_diagnostics"]
            if (horizon["baseline_status"] != "exploratory_current_history_only" or
                    horizon["ridge_status"] != "exploratory_current_history_only"):
                assert diagnostics is None
                continue
            assert diagnostics is not None
            assert diagnostics["garch_vs_ewma"]["nonoverlap_phase_count"] == length
            assert diagnostics["ridge_vs_ewma"]["nonoverlap_phase_count"] == length
            for name in ("garch_vs_ewma", "ridge_vs_ewma", "gjr_vs_garch"):
                assert (diagnostics[name]["block_2h_ci_percentage_points"] is not None) == (
                    count >= 4 * length
                )
            assert horizon["mae_daily_volatility_percentage_points"]["gjr"] is not None
            assert horizon["paired_block_ci_difference_vs_ewma_percentage_points"]["gjr"]
            assert horizon["paired_block_ci_difference_vs_garch_percentage_points"]["gjr"]

    path = base / "SPY" / "capture.csv"
    path.write_bytes(path.read_bytes().replace(b"1000", b"1001", 1))
    with pytest.raises(ValueError, match="hash does not match"):
        run_analysis(manifest, holdout_start=date(2025, 1, 2))

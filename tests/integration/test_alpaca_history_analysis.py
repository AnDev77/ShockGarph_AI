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
        for horizon in asset["horizons"]:
            count = horizon["holdout_prediction_dates"]
            length = horizon["horizon_sessions"]
            assert horizon["nonoverlapping_windows"] == (count + length - 1) // length
            assert horizon["conservative_full_start_blocks"] == count // length

    path = base / "SPY" / "capture.csv"
    path.write_bytes(path.read_bytes().replace(b"1000", b"1001", 1))
    with pytest.raises(ValueError, match="hash does not match"):
        run_analysis(manifest, holdout_start=date(2025, 1, 2))

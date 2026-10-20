from __future__ import annotations

import csv
import hashlib
import math
from datetime import date, timedelta
from pathlib import Path

import pytest

from scripts.evaluate_exploratory_history import run_history


def test_private_csv_report_records_provenance_and_limits(tmp_path: Path) -> None:
    source = tmp_path / "tlt-private.csv"
    with source.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(("session_date", "adjusted_close"))
        for index in range(100):
            writer.writerow((date(2024, 1, 1) + timedelta(days=index), 100 * math.exp(index / 100)))
    report = run_history(source, source="private-test", holdout_start=date(2024, 2, 1))

    assert report["source_file_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert report["observation_count"] == 100
    assert report["status"] == "exploratory_current_history_only"
    assert not report["historical_price_vintages_verified"]
    assert not report["public_performance_allowed"]
    assert report["horizons"][1]["sample_size"] == 49

    model_report = run_history(
        source, source="private-test", holdout_start=date(2024, 2, 1), compare_model=True
    )
    assert model_report["source_file_sha256"] == report["source_file_sha256"]
    assert model_report["candidate_model"]["horizons"][1]["status"] == (
        "insufficient_training_or_holdout"
    )

    source.write_text("session_date,adjusted_close\n2024-01-01,nan\n", encoding="utf-8")
    with pytest.raises(ValueError, match="positive and finite"):
        run_history(source, source="private-test", holdout_start=date(2024, 1, 1))

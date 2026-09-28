from datetime import UTC, datetime, timedelta

import pytest
from shockgraph_analytics.price_baseline import evaluate_price_baseline


def _rows(count: int) -> list[dict[str, object]]:
    return [
        {
            "event_id": f"cpi-{index:02d}",
            "release_at": datetime(2023, 1, 1, tzinfo=UTC) + timedelta(days=30 * index),
            "asset_id": asset,
            "horizon": horizon,
            "return_value": float(index) / 100,
        }
        for index in range(count)
        for asset in ("SPY", "TLT", "GLD")
        for horizon in ("m5", "m30")
    ]


def test_baseline_uses_only_earlier_events_and_abstains_with_small_test_sample() -> None:
    result = evaluate_price_baseline(_rows(3), min_train=2, min_test=10)
    assert result["status"] == "insufficient_test_events"
    assert result["common_events"] == 3
    assert len(result["predictions"]) == 6
    assert all(row["predicted_return"] == pytest.approx(0.005) for row in result["predictions"])
    assert all(row["train_events"] == 2 for row in result["predictions"])
    assert result["metrics"] == {}


def test_baseline_reports_out_of_sample_metrics_when_gate_passes() -> None:
    result = evaluate_price_baseline(_rows(12), min_train=2, min_test=10)
    assert result["status"] == "evaluated"
    assert result["metrics"]["SPY:m5"]["test_events"] == 10
    assert result["metrics"]["SPY:m5"]["mae"] < result["metrics"]["SPY:m5"]["zero_mae"]


def test_baseline_rejects_unbalanced_or_duplicate_event_rows() -> None:
    rows = _rows(3)
    with pytest.raises(ValueError, match="six unique"):
        evaluate_price_baseline(rows[:-1])
    with pytest.raises(ValueError, match="six unique"):
        evaluate_price_baseline(rows + [rows[0]])

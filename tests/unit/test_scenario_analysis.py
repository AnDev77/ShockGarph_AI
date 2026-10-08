from __future__ import annotations

import pytest
from pydantic import ValidationError
from shockgraph_analytics.scenarios import ScenarioDataset, demo_dataset, scenario_report


def test_three_consensus_scenarios_and_quantiles_use_separate_past_events() -> None:
    dataset = demo_dataset()
    report = scenario_report(dataset, asset_id="SPY", horizon="m30")
    assert report["provenance"]["source_kind"] == "synthetic"
    assert report["interpretation"] == "historical_distribution_not_forecast"
    rows = report["scenarios"]
    assert {row["scenario"] for row in rows} == {"above", "inline", "below"}
    assert sum(row["implied_probability"] for row in rows) == pytest.approx(1)
    assert [row["sample_count"] for row in rows] == [12, 12, 12]
    for row in rows:
        assert row["status"] == "ready"
        q = row["quantiles"]
        assert q["q10"] <= q["q25"] <= q["q50"] <= q["q75"] <= q["q90"]
        assert "expected_return" not in row
    assert "event_returns" not in report and "event_ids" not in report


def test_empirical_quantile_uses_inverse_cdf_and_small_samples_are_withheld() -> None:
    dataset = demo_dataset()
    payload = dataset.model_dump(mode="json")
    payload["observations"] = payload["observations"][:3]
    for index, row in enumerate(payload["observations"]):
        row["actual_mom"] = row["consensus_mom"] + 0.1
        row["returns"]["SPY:m30"] = [-0.02, 0.01, 0.03][index]
    limited = ScenarioDataset.model_validate(payload)
    hidden = scenario_report(limited, asset_id="SPY", horizon="m30")
    assert hidden["scenarios"][0]["quantiles"] is None
    assert hidden["scenarios"][0]["status"] == "insufficient_data"
    shown = scenario_report(limited, asset_id="SPY", horizon="m30", min_sample=2)
    assert shown["scenarios"][0]["quantiles"] == {
        "q10": -0.02,
        "q25": -0.02,
        "q50": 0.01,
        "q75": 0.03,
        "q90": 0.03,
    }


@pytest.mark.parametrize("failure", ["late_consensus", "future_label", "duplicate", "nan"])
def test_invalid_history_is_rejected_before_reporting(failure: str) -> None:
    payload = demo_dataset().model_dump(mode="json")
    row = payload["observations"][0]
    if failure == "late_consensus":
        row["consensus_available_at"] = row["release_at"]
    elif failure == "future_label":
        row["returns_available_at"] = "2030-01-01T00:00:00Z"
    elif failure == "duplicate":
        payload["observations"].append(row.copy())
    else:
        row["returns"]["SPY:m30"] = float("nan")
    with pytest.raises(ValidationError):
        ScenarioDataset.model_validate(payload)


def test_real_snapshot_requires_publication_authorization_and_exact_boundaries() -> None:
    payload = demo_dataset().model_dump(mode="json")
    payload["source_kind"] = "licensed_historical"
    with pytest.raises(ValidationError):
        ScenarioDataset.model_validate(payload)
    payload.update(publication_authorized=True, authorization_reference="test-only-record")
    payload["consensus"]["expected_mom"] = 0.4
    with pytest.raises(ValidationError):
        ScenarioDataset.model_validate(payload)


def test_report_rejects_unsupported_asset_and_horizon() -> None:
    dataset = demo_dataset()
    for asset, horizon in [("GLD", "m30"), ("SPY", "d5")]:
        with pytest.raises(ValueError):
            scenario_report(dataset, asset_id=asset, horizon=horizon)

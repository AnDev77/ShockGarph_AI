from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from shockgraph_analytics.contracts import ResearchDataset
from shockgraph_analytics.evaluation import (
    empirical_crps,
    evaluate,
    forecast,
    prepare,
    scenario_weights,
    tail_risk,
)
from shockgraph_analytics.probability import (
    binary_book_midpoint,
    normalize_verified_partition,
    thresholds_to_partition,
)


def test_binary_orderbook_spread_is_not_a_probability_overround() -> None:
    quote = binary_book_midpoint(yes_bid=0.60, no_bid=0.30)
    assert quote["yes_midpoint"] == pytest.approx(0.65)
    assert quote["no_midpoint"] == pytest.approx(0.35)
    assert quote["spread"] == pytest.approx(0.10)
    with pytest.raises(ValueError, match="crossed"):
        binary_book_midpoint(0.8, 0.3)


def test_verified_partition_normalizes_and_abstains_on_bad_coverage() -> None:
    result = normalize_verified_partition(
        {"below": 0.42, "at_or_above": 0.60}, partition_verified=True
    )
    assert sum(result["probabilities"].values()) == pytest.approx(1)
    assert result["probabilities"]["below"] == pytest.approx(0.42 / 1.02)
    assert result["raw_sum"] == pytest.approx(1.02)
    with pytest.raises(ValueError, match="verified"):
        normalize_verified_partition({"below": 0.4, "at_or_above": 0.6})
    with pytest.raises(ValueError, match="deviation"):
        normalize_verified_partition({"below": 0.1, "at_or_above": 0.2}, partition_verified=True)


def test_overlapping_thresholds_become_disjoint_intervals_only_if_monotone() -> None:
    assert thresholds_to_partition([0.3, 0.5], [0.7, 0.2]) == pytest.approx([0.3, 0.5, 0.2])
    with pytest.raises(ValueError, match="strictly increasing"):
        thresholds_to_partition([0.5, 0.3], [0.7, 0.2])
    with pytest.raises(ValueError, match="monotone"):
        thresholds_to_partition([0.3, 0.5], [0.2, 0.7])


def test_conditional_shrinkage_pools_sparse_scenarios_without_future_data() -> None:
    weights = scenario_weights([True, True, False, False], 1.0, strength=4)
    assert weights == pytest.approx([1 / 3, 1 / 3, 1 / 6, 1 / 6])
    assert sum(weights) == pytest.approx(1)


def test_tail_risk_requires_ten_effective_tail_observations() -> None:
    small = tail_risk([-0.1] + [0.01] * 19, [0.05] * 20)
    assert small["status"] == "insufficient_tail_data"
    assert "var95" not in small and "es95" not in small
    values = [-0.1] * 10 + [0.01] * 190
    large = tail_risk(values, [1 / 200] * 200)
    assert large["status"] == "exploratory"
    assert large["var95"] == pytest.approx(0.1)
    assert large["es95"] == pytest.approx(0.1)


def dataset_payload(count: int = 8) -> dict:
    releases, snapshots, prices = [], [], []
    for i in range(count):
        release = datetime(2020, 1, 15, 13, 30, tzinfo=UTC) + timedelta(days=30 * i)
        prediction = release - timedelta(hours=17)
        end = release + timedelta(hours=7, minutes=30)
        event_id = f"synthetic-{i}"
        releases.append(
            {
                "event_id": event_id,
                "prediction_at": prediction.isoformat(),
                "release_at": release.isoformat(),
                "return_start_at": prediction.isoformat(),
                "return_end_at": end.isoformat(),
                "outcome_available_at": (release + timedelta(minutes=1)).isoformat(),
                "actual_value": 0.4 if i % 2 else 0.2,
                "expected_value": 0.3,
                "expectation_available_at": prediction.isoformat(),
                "raw_hash": "a" * 64,
            }
        )
        snapshots.append(
            {
                "event_id": event_id,
                "market_ticker": f"contract-{i}",
                "observed_at": prediction.isoformat(),
                "available_at": prediction.isoformat(),
                "probability": 0.7,
                "raw_hash": "b" * 64,
            }
        )
        for asset in ("SPY", "TLT", "GLD"):
            for instant, price in ((prediction, 100), (end, 98 if i % 2 else 101)):
                prices.append(
                    {
                        "asset_id": asset,
                        "price_at": instant.isoformat(),
                        "available_at": instant.isoformat(),
                        "price": price,
                        "raw_hash": "c" * 64,
                    }
                )
    return {
        "source_kind": "synthetic",
        "definition": "synthetic CPI MoM > 0.3 percent",
        "threshold": 0.3,
        "assets": ["SPY", "TLT", "GLD"],
        "weights": [0.5, 0.3, 0.2],
        "currency": "USD",
        "price_basis": "adjusted_close",
        "releases": releases,
        "snapshots": snapshots,
        "prices": prices,
        "evaluation_at": "2022-01-01T00:00:00Z",
    }


def test_crps_matches_hand_calculation() -> None:
    assert empirical_crps([-1.0, 1.0], [0.5, 0.5], 0.0) == pytest.approx(0.5)
    assert empirical_crps([2.0], [1.0], 0.0) == 2
    with pytest.raises(ValueError):
        empirical_crps([1.0], [0.5], 0.0)


def test_walk_forward_uses_only_mature_past_releases_and_compares_same_events() -> None:
    result = evaluate(ResearchDataset.model_validate(dataset_payload()), min_train=4)
    assert result["status"] == "synthetic_only"
    assert result["evaluated_events"] == 4
    for fold in result["folds"]:
        assert fold["event_id"] not in fold["train_event_ids"]
        if fold["status"] == "skipped":
            continue
        assert len(fold["train_event_ids"]) >= 4
        assert set(fold["scores"]) == {"SPY", "TLT", "GLD", "portfolio"}
    assert result["comparison"]["portfolio"]["independent_events"] == 4


def test_post_release_probability_is_not_selected_before_settlement() -> None:
    payload = dataset_payload()
    future = dict(payload["snapshots"][0])
    future.update(
        observed_at=payload["releases"][0]["release_at"],
        available_at=payload["releases"][0]["release_at"],
        probability=1.0,
    )
    payload["snapshots"].append(future)
    prepared, _ = prepare(ResearchDataset.model_validate(payload))
    assert prepared[0].probability == 0.7


def test_missing_asset_endpoint_excludes_whole_event() -> None:
    payload = dataset_payload()
    payload["prices"].pop(5)
    prepared, coverage = prepare(ResearchDataset.model_validate(payload))
    assert len(prepared) == 7
    assert coverage[0]["reason"] == "missing_price:GLD"


def test_late_labels_are_not_used_to_train_earlier_fold() -> None:
    payload = dataset_payload()
    payload["releases"][0]["outcome_available_at"] = "2021-01-01T00:00:00Z"
    result = evaluate(ResearchDataset.model_validate(payload), min_train=4)
    assert all("synthetic-0" not in f["train_event_ids"] for f in result["folds"])


def test_absent_scenario_abstains_instead_of_inventing_distribution() -> None:
    payload = dataset_payload()
    for row in payload["releases"]:
        row["actual_value"] = 0.4
    result = evaluate(ResearchDataset.model_validate(payload), min_train=4)
    assert result["evaluated_events"] == 0
    assert result["comparison"] == {}
    assert result["folds"][4]["reason"] == "insufficient_scenario_samples"


def test_duplicate_release_and_conflicting_price_rejected() -> None:
    payload = dataset_payload()
    payload["releases"].append(payload["releases"][0])
    with pytest.raises(ValueError, match="duplicate event"):
        ResearchDataset.model_validate(payload)
    payload = dataset_payload()
    duplicate = dict(payload["prices"][0], price=101)
    payload["prices"].append(duplicate)
    with pytest.raises(ValueError, match="duplicate price"):
        ResearchDataset.model_validate(payload)


@pytest.mark.parametrize(
    "field,value",
    [("probability", float("nan")), ("probability", 1.1), ("observed_at", "2020-01-01T00:00:00")],
)
def test_invalid_probability_or_timestamp_rejected(field, value) -> None:
    payload = dataset_payload()
    payload["snapshots"][0][field] = value
    with pytest.raises(ValueError):
        ResearchDataset.model_validate(payload)


def test_weights_and_prediction_time_rejected() -> None:
    payload = dataset_payload()
    payload["weights"] = [0.5, 0.3, 0.3]
    with pytest.raises(ValueError, match="weights"):
        ResearchDataset.model_validate(payload)
    payload = dataset_payload()
    payload["releases"][0]["prediction_at"] = payload["releases"][0]["release_at"]
    with pytest.raises(ValueError, match="prediction"):
        ResearchDataset.model_validate(payload)


def test_future_targets_are_pending_and_cannot_enter_metrics() -> None:
    payload = dataset_payload()
    payload["evaluation_at"] = payload["releases"][0]["prediction_at"]
    result = evaluate(ResearchDataset.model_validate(payload), min_train=4)
    assert result["evaluated_events"] == 0
    assert all(row["reason"] == "pending_outcome" for row in result["coverage"])


def test_stale_or_late_available_inputs_are_excluded() -> None:
    payload = dataset_payload()
    payload["snapshots"][0]["available_at"] = payload["releases"][0]["release_at"]
    payload["releases"][1]["expectation_available_at"] = payload["releases"][1]["release_at"]
    _, coverage = prepare(ResearchDataset.model_validate(payload))
    assert coverage[0]["reason"] == "missing_pre_release_probability"
    assert coverage[1]["reason"] == "late_expectation"


def test_future_outcomes_do_not_change_earlier_predictions_and_run_is_deterministic() -> None:
    original = evaluate(ResearchDataset.model_validate(dataset_payload()), min_train=4)
    payload = dataset_payload()
    payload["releases"][-1]["actual_value"] = 2.0
    changed = evaluate(ResearchDataset.model_validate(payload), min_train=4)
    assert original["folds"][4]["predictions"] == changed["folds"][4]["predictions"]
    assert original == evaluate(ResearchDataset.model_validate(dataset_payload()), min_train=4)


def test_joint_asset_vectors_preserve_offsetting_portfolio_returns() -> None:
    payload = dataset_payload()
    payload["weights"] = [0.5, 0.5, 0.0]
    for i in range(8):
        payload["prices"][i * 6 + 3]["price"] = 200 - payload["prices"][i * 6 + 1]["price"]
    result = evaluate(ResearchDataset.model_validate(payload), min_train=4)
    f = result["folds"][4]["predictions"]["portfolio"]["probability_weighted"]
    assert f["mean_return"] == pytest.approx(0.0, abs=1e-15)
    assert f["predictive_std"] == pytest.approx(0.0, abs=1e-15)


def test_weighted_distribution_changes_with_probability_only() -> None:
    assert forecast([-0.02, 0.01], [0.7, 0.3])["mean_return"] == pytest.approx(-0.011)
    assert forecast([-0.02, 0.01], [0.7, 0.3])["probability_up"] == pytest.approx(0.3)
    payload = dataset_payload()
    payload["snapshots"][4]["probability"] = 0.0
    result = evaluate(ResearchDataset.model_validate(payload), min_train=4)
    f = result["folds"][4]["predictions"]["SPY"]["probability_weighted"]
    assert f["mean_return"] == pytest.approx(0.0)
    assert f["q05"] == pytest.approx(-0.02)


def test_crps_sorted_formula_matches_pairwise_definition() -> None:
    values, weights, target = [-3.0, 1.0, 2.0], [0.1, 0.3, 0.6], 0.25
    expected = sum(w * abs(v - target) for v, w in zip(values, weights, strict=True))
    expected -= 0.5 * sum(
        weights[i] * weights[j] * abs(values[i] - values[j]) for i in range(3) for j in range(3)
    )
    assert empirical_crps(values, weights, target) == pytest.approx(expected)


def test_stale_snapshot_and_late_pre_event_price_are_rejected() -> None:
    payload = dataset_payload()
    payload["snapshots"][0]["observed_at"] = "2020-01-01T00:00:00Z"
    payload["prices"][6]["available_at"] = payload["releases"][1]["release_at"]
    _, coverage = prepare(ResearchDataset.model_validate(payload))
    assert coverage[0]["reason"] == "missing_pre_release_probability"
    assert coverage[1]["reason"] == "late_start_price:SPY"

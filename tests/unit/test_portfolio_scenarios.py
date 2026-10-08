from __future__ import annotations

import pytest
from pydantic import ValidationError
from shockgraph_analytics.portfolio import PortfolioWeights, portfolio_report
from shockgraph_analytics.scenarios import ScenarioDataset, demo_dataset


def small_dataset(pairs: list[tuple[float, float]]) -> ScenarioDataset:
    payload = demo_dataset().model_dump(mode="json")
    payload["observations"] = payload["observations"][:6]
    for row, (spy, tlt) in zip(payload["observations"], pairs, strict=True):
        row["returns"]["SPY:m30"] = spy
        row["returns"]["TLT:m30"] = tlt
    return ScenarioDataset.model_validate(payload)


def test_joint_event_pairing_preserves_perfect_offset_instead_of_marginal_quantiles():
    dataset = small_dataset([(0.1, -0.1), (-0.2, 0.2)] * 3)
    report = portfolio_report(
        dataset, weights=PortfolioWeights(spy=0.5, tlt=0.5), horizon="m30", min_sample=2
    )
    result = report["result"]
    assert result["expected_return"] == pytest.approx(0)
    assert result["probability_flat"] == pytest.approx(1)
    assert result["probability_up"] == result["probability_down"] == 0
    assert set(result["quantiles"].values()) == {0}
    assert all(set(row["quantiles"].values()) == {0} for row in report["scenarios"])


def test_mixture_probabilities_and_quantiles_match_hand_calculated_distribution():
    # above ±10% weighs 0.4, inline 0% weighs 0.35, below ±20% weighs 0.25.
    pairs = [(-0.1, -0.1), (0, 0), (-0.2, -0.2), (0.1, 0.1), (0, 0), (0.2, 0.2)]
    report = portfolio_report(
        small_dataset(pairs),
        weights=PortfolioWeights(spy=0.6, tlt=0.4),
        horizon="m30",
        min_sample=2,
        portfolio_value=1000,
    )
    result = report["result"]
    assert result["expected_return"] == pytest.approx(0)
    assert result["probability_up"] == pytest.approx(0.325)
    assert result["probability_down"] == pytest.approx(0.325)
    assert result["probability_flat"] == pytest.approx(0.35)
    assert result["quantiles"] == pytest.approx(
        {
            "q10": -0.2,
            "q25": -0.1,
            "q50": 0,
            "q75": 0.1,
            "q90": 0.2,
        }
    )
    assert result["amount_range_usd"] == pytest.approx([-200, 200])
    assert report["total_event_count"] == 6
    assert "event_returns" not in report


def test_weights_change_mean_and_preserve_linear_asset_contributions():
    dataset = small_dataset([(0.02, -0.04)] * 6)
    report = portfolio_report(
        dataset, weights=PortfolioWeights(spy=0.75, tlt=0.25), horizon="m30", min_sample=2
    )
    assert report["result"]["expected_return"] == pytest.approx(0.005)
    assert sum(a["return_contribution"] for a in report["assets"]) == pytest.approx(0.005)
    spy_only = portfolio_report(
        dataset, weights=PortfolioWeights(spy=1, tlt=0), horizon="m30", min_sample=2
    )
    assert spy_only["result"]["expected_return"] == pytest.approx(0.02)


def test_missing_positive_probability_scenario_withholds_entire_result():
    payload = demo_dataset().model_dump(mode="json")
    payload["observations"] = payload["observations"][:-3]
    report = portfolio_report(
        ScenarioDataset.model_validate(payload),
        weights=PortfolioWeights(spy=0.5, tlt=0.5),
        horizon="m30",
        min_sample=12,
    )
    assert report["status"] == "insufficient_data"
    assert report["result"] is None and report["assets"] == []
    assert report["unavailable_probability_mass"] == pytest.approx(1)


def test_one_missing_scenario_is_not_silently_renormalized():
    payload = demo_dataset().model_dump(mode="json")
    del payload["observations"][33]  # above has 11 events, other scenarios have 12.
    report = portfolio_report(
        ScenarioDataset.model_validate(payload),
        weights=PortfolioWeights(spy=0.5, tlt=0.5),
        horizon="m30",
        min_sample=12,
    )
    assert report["unavailable_probability_mass"] == pytest.approx(0.4)
    assert report["result"] is None


def test_empty_zero_probability_scenarios_do_not_block_valid_mixture():
    payload = demo_dataset().model_dump(mode="json")
    payload["quotes"][0]["probability_above"] = 1
    payload["quotes"][1]["probability_above"] = 0
    payload["observations"] = [
        row for row in payload["observations"] if row["actual_mom"] == row["consensus_mom"]
    ]
    report = portfolio_report(
        ScenarioDataset.model_validate(payload),
        weights=PortfolioWeights(spy=0.5, tlt=0.5),
        horizon="m30",
    )
    assert report["status"] == "ready"
    assert report["unavailable_probability_mass"] == 0
    assert report["result"] is not None


@pytest.mark.parametrize("spy,tlt", [(-0.1, 1.1), (0.4, 0.4), (1.1, 0), (float("nan"), 0)])
def test_invalid_weights_rejected_without_renormalization(spy, tlt):
    with pytest.raises(ValidationError):
        PortfolioWeights(spy=spy, tlt=tlt)


def test_unsupported_horizon_and_nonfinite_or_negative_valuation_rejected():
    for args in [
        {"horizon": "d5"},
        {"horizon": "m30", "portfolio_value": -1},
        {"horizon": "m30", "portfolio_value": float("inf")},
        {"horizon": "m30", "min_sample": 1},
    ]:
        with pytest.raises(ValueError):
            portfolio_report(demo_dataset(), weights=PortfolioWeights(spy=0.5, tlt=0.5), **args)

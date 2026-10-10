from __future__ import annotations

from datetime import timedelta

import pytest
from shockgraph_analytics.serving import build_serving_dataset, demo_inputs


def test_builder_joins_first_releases_consensus_and_same_event_prices():
    inputs = demo_inputs()
    dataset, coverage = build_serving_dataset(**inputs)
    assert len(dataset.observations) == 36
    assert {row["status"] for row in coverage} == {"eligible"}
    first = dataset.observations[0]
    assert first.actual_mom == 0.4
    assert first.consensus_mom == 0.3
    assert first.returns["SPY:m30"] == pytest.approx(-0.0169)
    assert first.returns_available_at < dataset.as_of
    assert dataset.source_kind == "synthetic"


def test_missing_consensus_and_price_are_reported_without_filling_values():
    inputs = demo_inputs()
    absent = inputs["releases"][0]
    inputs["consensuses"] = [c for c in inputs["consensuses"] if c.event_id != absent.event_ticker]
    missing_price_event = inputs["releases"][1]
    inputs["bars"] = [
        b
        for b in inputs["bars"]
        if not (
            b.asset_id == "TLT"
            and b.price_at == missing_price_event.release_at + timedelta(minutes=30)
        )
    ]
    dataset, coverage = build_serving_dataset(**inputs)
    assert len(dataset.observations) == 34
    assert coverage[0]["status"] == "missing_consensus"
    assert coverage[1]["status"] == "missing_price"
    assert coverage[1]["missing_groups"] == ["TLT:m30"]


def test_late_consensus_and_unavailable_returns_do_not_enter_history():
    inputs = demo_inputs()
    event = inputs["releases"][0]
    index = next(i for i, c in enumerate(inputs["consensuses"]) if c.event_id == event.event_ticker)
    inputs["consensuses"][index] = inputs["consensuses"][index].model_copy(
        update={
            "available_at": event.release_at,
        }
    )
    bar = next(b for b in inputs["bars"] if b.asset_id == "SPY")
    inputs["bars"] = [
        b.model_copy(update={"available_at": inputs["as_of"] + timedelta(days=1)})
        if b is bar
        else b
        for b in inputs["bars"]
    ]
    dataset, coverage = build_serving_dataset(**inputs)
    assert len(dataset.observations) == 35
    assert coverage[0]["status"] == "late_consensus"


def test_historical_returns_received_after_cutoff_are_excluded():
    inputs = demo_inputs()
    bar = inputs["bars"][0]
    inputs["bars"][0] = bar.model_copy(update={"available_at": inputs["as_of"] + timedelta(days=1)})
    dataset, coverage = build_serving_dataset(**inputs)
    assert len(dataset.observations) == 35
    assert coverage[0]["status"] == "returns_not_available"


@pytest.mark.parametrize("kind", ["release", "consensus", "bar"])
def test_duplicate_sources_fail_instead_of_selecting_arbitrary_row(kind):
    inputs = demo_inputs()
    key = {"release": "releases", "consensus": "consensuses", "bar": "bars"}[kind]
    inputs[key].append(inputs[key][0])
    with pytest.raises(ValueError):
        build_serving_dataset(**inputs)


def test_target_event_and_future_releases_never_enter_training_history():
    inputs = demo_inputs()
    first = inputs["releases"][0]
    inputs["releases"][0] = first.model_copy(update={"event_ticker": inputs["target_event_id"]})
    inputs["releases"][1] = inputs["releases"][1].model_copy(
        update={
            "release_at": inputs["release_at"],
        }
    )
    dataset, coverage = build_serving_dataset(**inputs)
    assert len(dataset.observations) == 34
    assert [r["status"] for r in coverage[:2]] == ["target_event", "not_historical"]

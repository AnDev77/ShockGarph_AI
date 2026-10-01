from datetime import UTC, datetime, timedelta

import pytest
from shockgraph_analytics.kalshi_ablation import GROUPS, AblationEvent, summarize, walk_forward


def events(count=35):
    result = []
    for i in range(count):
        release = datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=31 * i)
        positive = i % 2 == 0
        result.append(
            AblationEvent(
                event_id=f"event-{i}",
                release_at=release,
                quote_at=release - timedelta(minutes=1),
                label_available_at=release + timedelta(minutes=30),
                probability=0.9 if positive else 0.1,
                outcome=positive,
                returns={g: 0.01 if positive else -0.01 for g in GROUPS},
            )
        )
    return result


def test_paired_probability_ablation_and_research_gate():
    sample = events()
    summary = summarize(sample, min_train=20)
    assert summary.test_events == 15
    assert summary.status == "exploratory"
    assert all(v.mean_crps_difference < 0 for v in summary.comparison.values())
    assert summarize(sample[:27], min_train=20).comparison == {}
    assert summarize(sample[:27], min_train=20).test_events == 7
    assert summarize(sample[:27], min_train=5).test_events == 22
    # Setting p to the train-only prior produces exactly identical distributions.
    prior = [
        e.model_copy(update={"probability": sum(x.outcome for x in sample[:i]) / i}) if i else e
        for i, e in enumerate(sample)
    ]
    assert all(
        v.mean_crps_difference == 0 for v in summarize(prior, min_train=20).comparison.values()
    )


def test_current_outcome_and_future_rows_do_not_enter_forecasts():
    sample = events()
    before = walk_forward(sample, min_train=5)
    changed = sample[:]
    changed[10] = changed[10].model_copy(update={"outcome": not changed[10].outcome})
    changed[11:] = [
        e.model_copy(update={"returns": {g: 0.5 for g in GROUPS}}) for e in changed[11:]
    ]
    after = walk_forward(changed, min_train=5)
    assert before[:11] == after[:11]
    delayed = sample[0].model_copy(update={"label_available_at": sample[10].release_at})
    folds = walk_forward([delayed, *sample[1:]], min_train=5)
    assert delayed.event_id not in folds[10]["train_event_ids"]
    assert delayed.event_id in folds[11]["train_event_ids"]


def test_missing_scenario_and_invalid_inputs():
    one_class = [e.model_copy(update={"outcome": True}) for e in events()]
    assert summarize(one_class, min_train=5).test_events == 0
    e = events(1)[0]
    with pytest.raises(ValueError, match="before release"):
        AblationEvent.model_validate({**e.model_dump(), "quote_at": e.release_at})
    with pytest.raises(ValueError, match="four primary"):
        AblationEvent.model_validate({**e.model_dump(), "returns": {"SPY:m5": 0.1}})
    with pytest.raises(ValueError, match="duplicate event"):
        walk_forward([e, e], min_train=5)
    assert summarize([], min_train=20).comparison == {}
    sensitivity = e.model_copy(
        update={
            "quote_at": e.release_at - timedelta(minutes=30),
            "quote_age_limit_minutes": 30,
        }
    )
    assert sensitivity.quote_age_limit_minutes == 30

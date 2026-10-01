from datetime import UTC, datetime, timedelta
from typing import Any

from evaluate_cpi_kalshi_sensitivity import POLICIES, select_quote


def _quote(release, minutes, spread, volume):
    return {
        "end_at": (release - timedelta(minutes=minutes)).isoformat(),
        "yes_midpoint": 0.5,
        "spread": spread,
        "volume": volume,
    }


def test_filter_policies_change_one_gate_and_combined_gate():
    release = datetime(2026, 1, 1, 13, 30, tzinfo=UTC)
    candidates = [
        _quote(release, 20, 0.14, 0),
        _quote(release, 10, 0.14, 2),
        _quote(release, 8, 0.08, 0),
        _quote(release, 5, 0.08, 2),
    ]
    selected: dict[str, dict[str, Any]] = {}
    for policy in POLICIES:
        quote, reason = select_quote(candidates, release, policy)
        assert reason == "accepted"
        assert quote is not None
        selected[policy.name] = quote
    assert selected["F0"]["quote_at"] == release - timedelta(minutes=5)
    assert selected["F1"]["quote_at"] == release - timedelta(minutes=5)
    assert selected["F2"]["quote_at"] == release - timedelta(minutes=5)
    assert selected["F3"]["quote_at"] == release - timedelta(minutes=5)
    assert selected["F4"]["quote_at"] == release - timedelta(minutes=5)

    cases = {
        "F1": [_quote(release, 20, 0.08, 2)],
        "F2": [_quote(release, 10, 0.14, 2)],
        "F3": [_quote(release, 10, 0.08, 0)],
        "F4": [_quote(release, 20, 0.14, None)],
    }
    by_name = {policy.name: policy for policy in POLICIES}
    assert select_quote(cases["F1"], release, by_name["F0"])[1] == "stale_before_release"
    assert select_quote(cases["F1"], release, by_name["F1"])[1] == "accepted"
    assert select_quote(cases["F2"], release, by_name["F2"])[1] == "accepted"
    assert select_quote(cases["F3"], release, by_name["F3"])[1] == "accepted"
    assert select_quote(cases["F4"], release, by_name["F4"])[1] == "accepted"


def test_quote_selector_rejects_future_and_invalid_values():
    release = datetime(2026, 1, 1, 13, 30, tzinfo=UTC)
    policy = POLICIES[0]
    assert select_quote([], release, policy)[1] == "no_structural_quote"
    assert select_quote([_quote(release, -1, 0.01, 1)], release, policy)[1] == (
        "at_or_after_release"
    )
    bad = _quote(release, 1, 0.01, 1)
    bad["yes_midpoint"] = float("nan")
    assert select_quote([bad], release, policy)[1] == "invalid_candidate"

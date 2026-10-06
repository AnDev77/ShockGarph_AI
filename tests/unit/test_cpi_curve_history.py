from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_cpi_curve_history import audit_history, synthetic_inputs  # noqa: E402


def test_universe_keeps_missing_events_and_reconstructs_original_quotes() -> None:
    releases, reports = synthetic_inputs()
    reports[0]["distribution"] = {"thresholds": [99], "bin_probabilities": [1]}
    result = audit_history(releases, reports)
    assert result["total_release_events"] == 4
    assert result["status_counts"] == {"eligible": 2, "abstained": 1, "missing_curve_report": 1}
    assert sum(result["status_counts"].values()) == 4
    assert result["quote_status_counts"] == {"eligible": 9}
    assert result["validated_inventory_events"] == 3
    assert result["events"][0]["exact_boundary_centers"] == [0.3, 0.4]
    assert result["events"][0]["threshold_count"] == 3
    assert result["events"][1]["max_isotonic_adjustment"] == pytest.approx(0.01)
    assert "exceeds declared limit" in result["events"][2]["curve_error"]
    assert result["consensus_status_counts"] == {"not_provided": 4}
    assert result["data_scope"] == "synthetic"


@pytest.mark.parametrize(
    "change",
    [
        "future_quote",
        "late_cutoff",
        "spread",
        "zero_volume",
        "inventory",
        "statuses",
        "ticker",
        "stale",
        "nan",
    ],
)
def test_invalid_inputs_abstain_without_silently_dropping_event(change: str) -> None:
    releases, reports = synthetic_inputs()
    report, quote = reports[0], reports[0]["quotes"][0]
    if change == "future_quote":
        quote["quote_end_at"] = releases[0]["release_at"]
    elif change == "late_cutoff":
        report["as_of"] = releases[0]["release_at"]
    elif change == "spread":
        quote["spread"] = 0.11
    elif change == "zero_volume":
        quote["volume"] = 0
    elif change == "inventory":
        report["inventory_markets"] = 99
    elif change == "statuses":
        report["quote_status_counts"] = {"eligible": 2}
    elif change == "ticker":
        quote["market_ticker"] = "OTHER-T0.2"
    elif change == "stale":
        quote["quote_end_at"] = "2025-01-15T13:00:00+00:00"
    else:
        quote["probability_above"] = float("nan")
    result = audit_history(releases, reports)
    assert len(result["events"]) == 4
    assert result["events"][0]["status"] == "abstained"


def test_rejection_counts_include_events_without_enough_quotes() -> None:
    releases, reports = synthetic_inputs()
    reports[0]["quotes"] = reports[0]["quotes"][:1]
    reports[0]["candidate_threshold_markets"] = 1
    reports[0]["quote_status_counts"] = {"eligible": 1}
    reports[0]["market_rejection_counts"] = {"unsupported_relation": 2}
    result = audit_history(releases, reports)
    assert result["events"][0]["status"] == "abstained"
    assert result["market_rejection_counts"] == {"unsupported_relation": 2}
    assert result["quote_status_counts"] == {"eligible": 7}


def test_freshness_is_measured_against_actual_release_not_only_cutoff() -> None:
    releases, reports = synthetic_inputs()
    quote = reports[0]["quotes"][0]
    quote["quote_end_at"] = "2025-01-15T13:15:00+00:00"
    assert audit_history(releases, reports)["events"][0]["status"] == "eligible"
    quote["quote_end_at"] = "2025-01-15T13:14:00+00:00"
    assert audit_history(releases, reports)["events"][0]["status"] == "abstained"


def test_consensus_requires_real_pre_cutoff_vintage_and_exact_boundaries() -> None:
    releases, reports = synthetic_inputs()
    consensus = {
        "event_id": releases[0]["event_ticker"],
        "expected_mom": 0.3,
        "available_at": "2025-01-15T12:00:00+00:00",
        "source": "synthetic-expert",
        "raw_hash": "a" * 64,
    }
    valid = audit_history(releases, reports, consensuses=[consensus])
    assert valid["events"][0]["consensus_status"] == "eligible"
    consensus["available_at"] = releases[0]["release_at"]
    assert (
        audit_history(releases, reports, consensuses=[consensus])["events"][0]["consensus_status"]
        == "abstained"
    )
    consensus["available_at"] = "2025-01-15T12:00:00+00:00"
    consensus["expected_mom"] = 0.5
    assert (
        audit_history(releases, reports, consensuses=[consensus])["events"][0]["consensus_status"]
        == "abstained"
    )


def test_duplicate_vintages_and_unknown_events_fail_explicitly() -> None:
    releases, reports = synthetic_inputs()
    with pytest.raises(ValueError, match="duplicate curve"):
        audit_history(releases, [*reports, reports[0]])
    with pytest.raises(ValueError, match="duplicate release"):
        audit_history([*releases, releases[0]], reports)
    with pytest.raises(ValueError, match="outside release universe"):
        audit_history(releases[1:], reports)


def test_actual_and_returns_never_affect_selection_and_inputs_are_not_mutated() -> None:
    releases, reports = synthetic_inputs()
    original = copy.deepcopy(reports)
    before = audit_history(releases, reports)
    releases[0].update(actual_mom_first=99, asset_return=0.9, kalshi_outcome="yes")
    assert audit_history(releases, reports) == before
    assert reports == original


def test_demo_cli_is_idempotent_and_real_mode_requires_authorization_record(tmp_path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/audit_cpi_curve_history.py"),
        "--demo",
        "--output-dir",
        str(tmp_path),
    ]
    first = subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, check=True, capture_output=True, text=True)
    assert first.stdout == second.stdout
    summary = json.loads(Path(json.loads(first.stdout)["report"]).read_text())
    assert summary["data_scope"] == "synthetic"
    assert summary["authorization_record_sha256"] is None
    assert len(summary["input_sha256"]) == 64
    assert len(list(tmp_path.rglob("report.json"))) == 1
    rejected = subprocess.run([sys.executable, command[1]], capture_output=True, text=True)
    assert rejected.returncode == 2
    assert "--authorization-record" in rejected.stderr

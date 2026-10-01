from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from shockgraph_api.app import create_app

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_cpi_asset_groups import evaluate_groups  # noqa: E402
from evaluate_cpi_kalshi_ablation import export_report  # noqa: E402
from evaluate_cpi_kalshi_sensitivity import export_report as export_sensitivity  # noqa: E402


def _csv(path: Path, rows: list[dict[str, object]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_group_evaluation_preserves_independent_samples_and_threshold(tmp_path: Path) -> None:
    releases = []
    probabilities = []
    bars = []
    for index in range(1, 17):
        year = 2024 + (index - 1) // 12
        month = (index - 1) % 12 + 1
        event_id = f"cpi-{year}-{month:02d}"
        ticker = f"KXCPI-{year % 100:02d}{date(year, month, 1):%b}".upper()
        next_year = year + (month == 12)
        next_month = month % 12 + 1
        release_day = f"{next_year}-{next_month:02d}-12"
        releases.append(
            {
                "event_id": event_id,
                "event_ticker": ticker,
                "reference_month": f"{year}-{month:02d}-01",
                "release_at": f"{release_day}T13:30:00+00:00",
                "actual_mom_first": 0.4 if index % 2 else 0.2,
                "threshold": 0.3,
                "bls_outcome": "yes" if index % 2 else "no",
                "source_url": (
                    "https://www.bls.gov/news.release/archives/"
                    f"cpi_{next_month:02d}12{next_year}.htm"
                ),
                "raw_hash": "a" * 64,
            }
        )
        probabilities.append(
            {
                "event_ticker": ticker,
                "status": "stale" if index == 16 else "eligible",
                "outcome": "yes" if index % 2 else "no",
                "quote_end_at": f"{release_day}T13:29:00+00:00",
                "probability_yes": 0.8 if index % 2 else 0.2,
                "spread": 0.02,
                "volume": 10,
            }
        )
        for asset in ("SPY", "TLT", "GLD"):
            if asset == "GLD" and index > 6:
                continue
            for minute, price in ((29, 100), (35, 101), ("00", 102)):
                timestamp = (
                    f"{release_day}T13:{minute}:00+00:00"
                    if isinstance(minute, int)
                    else f"{release_day}T14:00:00+00:00"
                )
                bars.append(
                    {
                        "asset_id": asset,
                        "price_at": timestamp,
                        "available_at": timestamp,
                        "open": price,
                        "high": price,
                        "low": price,
                        "close": price,
                        "volume": 10,
                        "extended_hours": "true",
                        "raw_hash": "b" * 64,
                    }
                )
    release_path = _csv(tmp_path / "releases.csv", releases)
    probability_path = _csv(tmp_path / "probabilities.csv", probabilities)
    bar_path = _csv(tmp_path / "bars.csv", bars)
    output = tmp_path / "report.json"
    report = json.loads(
        evaluate_groups(release_path, probability_path, bar_path, output).read_text()
    )

    assert report["group_results"]["SPY:m5"]["eligible_events"] == 15
    assert report["group_results"]["SPY:m5"]["test_events"] == 10
    assert report["group_results"]["SPY:m5"]["status"] == "evaluated"
    assert report["group_results"]["GLD:m5"]["eligible_events"] == 6
    assert report["group_results"]["GLD:m5"]["metrics"] == {}
    assert report["primary_cohort"]["assets"] == ["SPY", "TLT"]
    assert report["primary_cohort"]["common_eligible_events"] == 15
    assert report["primary_cohort"]["research_status"] == "insufficient_research_events"
    assert report["primary_cohort"]["research_additional_events_needed"] == 15
    assert report["supplemental_asset"] == "GLD"
    assert "return_value" not in output.read_text()
    assert evaluate_groups(release_path, probability_path, bar_path, output) == output
    ablation_path = tmp_path / "ablation.json"
    export_report(release_path, probability_path, bar_path, ablation_path)
    client = TestClient(create_app(ablation_report_path=ablation_path))
    payload = client.get("/v1/research/cpi-kalshi-ablation").json()
    assert payload["common_events"] == 15
    assert payload["research"]["comparison"] == {}
    assert payload["diagnostic"]["test_events"] == 10
    assert "return_value" not in ablation_path.read_text()
    assert "train_event_ids" not in ablation_path.read_text()
    view = client.get(
        "/v1/analysis",
        params={
            "asset_id": "SPY",
            "event_category": "CPI",
            "horizon": "m5",
        },
    ).json()
    assert view["independent_event_count"] == 15
    assert view["status"] == "exploratory"
    assert view["comparison"] is not None
    assert view["research_test_events"] == 0
    assert export_report(release_path, probability_path, bar_path, ablation_path) == ablation_path
    audit_events = []
    policy_cases = {
        13: ("13:10", 0.08, 10),
        14: ("13:20", 0.14, 10),
        15: ("13:20", 0.08, 0),
        16: ("13:10", 0.14, None),
    }
    for index, (release, probability) in enumerate(
        zip(releases, probabilities, strict=True), start=1
    ):
        quote_time, spread, volume = policy_cases.get(index, ("13:29", 0.02, 10))
        release_day = str(release["release_at"])[:10]
        audit_events.append(
            {
                "event_ticker": probability["event_ticker"],
                "outcome": probability["outcome"],
                "status": "no_eligible_candles" if index >= 13 else "eligible",
                "event_exclusion_reason": "synthetic_filter_failure" if index >= 13 else None,
                "quote_candidates": [
                    {
                        "end_at": f"{release_day}T{quote_time}:00+00:00",
                        "yes_midpoint": probability["probability_yes"],
                        "spread": spread,
                        "volume": volume,
                    }
                ],
            }
        )
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(
        json.dumps(
            {
                "series_ticker": "KXCPI",
                "events": audit_events,
                "candle_failure_counts": {"spread_above_0_10": 2},
                "candle_primary_exclusion_counts": {"spread_above_0_10": 2},
                "no_eligible_candle_event_reasons": {"spread_above_0_10": 2},
            }
        ),
        encoding="utf-8",
    )
    sensitivity_path = tmp_path / "sensitivity.json"
    sensitivity = json.loads(
        export_sensitivity(audit_path, release_path, bar_path, sensitivity_path).read_text()
    )
    assert {
        name: details["common_events"] for name, details in sensitivity["policies"].items()
    } == {"F0": 12, "F1": 13, "F2": 13, "F3": 13, "F4": 16}
    assert sensitivity["policies"]["F4"]["diagnostic"]["status"] == "exploratory"
    assert sensitivity["shared_with_f0"]["F4"]["diagnostic"]["status"] == (
        "insufficient_test_events"
    )
    assert sensitivity["audit_candle_failure_counts"] == {"spread_above_0_10": 2}
    assert sensitivity["audit_no_eligible_event_reasons"] == {"spread_above_0_10": 2}
    assert sensitivity["release_matched_no_eligible_event_reasons"] == {
        "synthetic_filter_failure": 4
    }
    assert "return_value" not in sensitivity_path.read_text()
    assert "train_event_ids" not in sensitivity_path.read_text()
    assert export_sensitivity(audit_path, release_path, bar_path, sensitivity_path) == (
        sensitivity_path
    )
    # Contract-cutoff eligibility must not override actual BLS release timing.
    for index, quote_time in enumerate(("13:14", "13:30", "13:31", "13:15")):
        probabilities[index]["quote_end_at"] = str(probabilities[index]["quote_end_at"]).replace(
            "13:29", quote_time
        )
    aligned_probability_path = _csv(tmp_path / "aligned_probabilities.csv", probabilities)
    aligned_path = tmp_path / "aligned_ablation.json"
    export_report(release_path, aligned_probability_path, bar_path, aligned_path)
    aligned = json.loads(aligned_path.read_text())
    assert aligned["common_events"] == 12
    assert aligned["selection_counts"] == {
        "input_events": 16,
        "probability_unavailable": 1,
        "incomplete_asset_windows": 0,
        "stale_before_release": 1,
        "at_or_after_release": 2,
        "accepted": 12,
    }
    assert len(aligned["quote_time_exclusions"]) == 3
    assert aligned["diagnostic"]["comparison"] == {}
    aligned_client = TestClient(create_app(ablation_report_path=aligned_path))
    aligned_view = aligned_client.get(
        "/v1/analysis", params={"asset_id": "SPY", "event_category": "CPI", "horizon": "m5"}
    ).json()
    assert aligned_view["status"] == "insufficient_data"
    assert aligned_view["independent_event_count"] == 12
    bad_report = json.loads(ablation_path.read_text())
    bad_report["research"]["status"] = "exploratory"
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(bad_report))
    bad_client = TestClient(create_app(ablation_report_path=invalid))
    assert bad_client.get("/v1/research/cpi-kalshi-ablation").status_code == 503
    bars[0]["volume"] = 11
    _csv(bar_path, bars)
    with pytest.raises(ValueError, match="existing group report differs"):
        evaluate_groups(release_path, probability_path, bar_path, output)
    with pytest.raises(ValueError, match="existing ablation report differs"):
        export_report(release_path, probability_path, bar_path, ablation_path)

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_kalshi_cpi import score_event_probabilities  # noqa: E402
from collect_bls_cpi_vintages import reconcile_probability_events  # noqa: E402


def test_reconciliation_excludes_nonmonthly_release_from_historical_baseline() -> None:
    events: list[dict[str, Any]] = [
        {
            "event_ticker": f"KXCPI-VALID-{index}",
            "market_ticker": f"KXCPI-VALID-{index}-T0.3",
            "outcome": "yes" if index % 2 == 0 else "no",
            "status": "no_eligible_candles",
        }
        for index in range(10)
    ]
    events.extend(
        [
            {
                "event_ticker": "KXCPI-NONMONTHLY",
                "market_ticker": "KXCPI-NONMONTHLY-T0.3",
                "outcome": "no",
                "status": "stale",
            },
            {
                "event_ticker": "KXCPI-CURRENT",
                "market_ticker": "KXCPI-CURRENT-T0.3",
                "outcome": "yes",
                "status": "eligible",
                "probability_yes": 0.8,
            },
        ]
    )
    validated = {
        **{event["event_ticker"]: event["outcome"] for event in events[:10]},
        "KXCPI-CURRENT": "yes",
    }

    reconciled = reconcile_probability_events(events, validated)
    result = score_event_probabilities(reconciled, min_history=10)

    assert len(reconciled) == 11
    assert result["comparisons"][0]["prior_events"] == 10
    assert result["comparisons"][0]["expanding_historical_probability"] == pytest.approx(0.5)


def test_reconciliation_rejects_a_different_bls_outcome() -> None:
    events = [
        {
            "event_ticker": "KXCPI-TEST",
            "market_ticker": "KXCPI-TEST-T0.3",
            "outcome": "yes",
            "status": "eligible",
            "probability_yes": 0.8,
        }
    ]
    with pytest.raises(ValueError, match="outcome mismatch"):
        reconcile_probability_events(events, {"KXCPI-TEST": "no"})

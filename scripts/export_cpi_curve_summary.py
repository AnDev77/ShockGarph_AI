from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def summarize_curve_report(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("schema_version") != "kalshi-cpi-threshold-curve-v1":
        raise ValueError("unsupported CPI curve report schema")
    distribution = report.get("distribution")
    curve = None
    if distribution is not None:
        if not isinstance(distribution, dict) or not isinstance(
            distribution.get("thresholds"), list
        ):
            raise ValueError("invalid CPI curve distribution")
        curve = {
            "threshold_count": len(distribution["thresholds"]),
            "raw_monotone": distribution.get("raw_monotone"),
            "max_isotonic_adjustment": distribution.get("max_isotonic_adjustment"),
            "max_quote_age_minutes": distribution.get("max_quote_age_minutes"),
            "method": distribution.get("method"),
        }
    return {
        "schema_version": "kalshi-cpi-threshold-curve-summary-v1",
        "event_ticker": report.get("event_ticker"),
        "as_of": report.get("as_of"),
        "status": report.get("status"),
        "inventory_markets": report.get("inventory_markets"),
        "candidate_threshold_markets": report.get("candidate_threshold_markets"),
        "market_rejection_counts": report.get("market_rejection_counts"),
        "quote_status_counts": report.get("quote_status_counts"),
        "curve_error": report.get("curve_error"),
        "curve": curve,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Kalshi CPI 확률곡선의 비원시 CI 요약 생성")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("CPI curve report must be an object")
    summary = summarize_curve_report(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"summary": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

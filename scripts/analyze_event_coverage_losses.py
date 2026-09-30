from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"CSV rows required: {path}")
    return rows


def analyze_losses(
    release_path: Path,
    probability_path: Path,
    asset_coverage_path: Path,
    asset_metadata_path: Path,
    panel_metadata_path: Path,
    output_path: Path,
    *,
    min_train: int = 5,
    min_test: int = 10,
) -> Path:
    if min_train < 1 or min_test < 1:
        raise ValueError("minimum train and test events must be positive")
    releases = _csv_rows(release_path)
    probabilities = _csv_rows(probability_path)
    asset_coverage = _json_object(asset_coverage_path)
    asset_metadata = _json_object(asset_metadata_path)
    panel_metadata = _json_object(panel_metadata_path)

    probability_by_ticker = {row["event_ticker"]: row for row in probabilities}
    if len(probability_by_ticker) != len(probabilities):
        raise ValueError("probability event tickers must be unique")
    asset_complete = set(asset_metadata.get("common_event_ids", []))
    model_common = set(panel_metadata.get("common_event_ids", []))
    if not model_common <= asset_complete:
        raise ValueError("model common events must be a subset of asset complete events")

    failures_by_event: dict[str, list[dict[str, str]]] = defaultdict(list)
    coverage_rows = asset_coverage.get("coverage")
    if not isinstance(coverage_rows, list):
        raise ValueError("asset coverage rows required")
    for row in coverage_rows:
        if not isinstance(row, dict):
            raise ValueError("asset coverage row must be an object")
        failures_by_event[str(row["event_id"])].append(
            {
                "asset_id": str(row["asset_id"]),
                "horizon": str(row["horizon"]),
                "status": str(row["status"]),
            }
        )

    stage_counts: Counter[str] = Counter()
    probability_status_counts: Counter[str] = Counter()
    price_failure_counts: Counter[str] = Counter()
    price_failure_asset_counts: Counter[str] = Counter()
    event_rows: list[dict[str, Any]] = []
    for release in releases:
        event_id = release["event_id"]
        probability = probability_by_ticker.get(release["event_ticker"])
        probability_status = probability["status"] if probability else "missing_probability_event"
        probability_eligible = probability_status == "eligible"
        price_complete = event_id in asset_complete
        included = event_id in model_common
        failures = sorted(
            failures_by_event.get(event_id, []),
            key=lambda row: (row["asset_id"], row["horizon"], row["status"]),
        )
        if included:
            stage = "included"
        elif price_complete:
            stage = "probability_only_loss"
        elif probability_eligible:
            stage = "price_only_loss"
        else:
            stage = "probability_and_price_loss"
        stage_counts[stage] += 1
        probability_status_counts[probability_status] += 1
        for failure in failures:
            price_failure_counts[failure["status"]] += 1
            price_failure_asset_counts[f"{failure['asset_id']}:{failure['status']}"] += 1
        event_rows.append(
            {
                "event_id": event_id,
                "reference_month": release["reference_month"],
                "probability_status": probability_status,
                "price_complete": price_complete,
                "model_included": included,
                "exclusion_stage": stage,
                "price_failures": failures,
            }
        )

    required_common = min_train + min_test
    summary = {
        "schema_version": "event-coverage-loss-diagnostic-v1",
        "release_events": len(releases),
        "probability_eligible_events": probability_status_counts["eligible"],
        "asset_complete_events": len(asset_complete),
        "model_common_events": len(model_common),
        "minimum_train_events": min_train,
        "minimum_test_events": min_test,
        "required_model_common_events": required_common,
        "additional_model_common_events_needed": max(0, required_common - len(model_common)),
        "exclusion_stage_counts": dict(sorted(stage_counts.items())),
        "probability_status_counts": dict(sorted(probability_status_counts.items())),
        "price_failure_counts": dict(sorted(price_failure_counts.items())),
        "price_failure_asset_counts": dict(sorted(price_failure_asset_counts.items())),
        "events": event_rows,
        "publication_boundary": "no_credentials_prices_returns_or_probability_values",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="CPI 확률·가격 사건 교집합의 표본 손실 진단")
    parser.add_argument("--releases", type=Path, required=True)
    parser.add_argument("--probabilities", type=Path, required=True)
    parser.add_argument("--asset-coverage", type=Path, required=True)
    parser.add_argument("--asset-metadata", type=Path, required=True)
    parser.add_argument("--panel-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-train", type=int, default=5)
    parser.add_argument("--min-test", type=int, default=10)
    args = parser.parse_args()
    output = analyze_losses(
        args.releases,
        args.probabilities,
        args.asset_coverage,
        args.asset_metadata,
        args.panel_metadata,
        args.output,
        min_train=args.min_train,
        min_test=args.min_test,
    )
    print(json.dumps({"event_loss_diagnostic": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

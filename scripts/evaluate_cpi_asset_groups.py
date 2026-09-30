from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/event_study"))

from build_cpi_asset_panel import _load_bars, _load_releases, _read_csv  # noqa: E402
from shockgraph_analytics.paper_panel import build_asset_windows  # noqa: E402
from shockgraph_analytics.price_baseline import KEYS  # noqa: E402


def evaluate_groups(
    release_path: Path,
    probability_path: Path,
    asset_bar_path: Path,
    output_path: Path,
    *,
    min_train: int = 5,
    min_test: int = 10,
) -> Path:
    if min_train < 1 or min_test < 1:
        raise ValueError("minimum train and test counts must be positive")
    releases = _load_releases(release_path)
    probabilities = _read_csv(probability_path)
    by_ticker = {row["event_ticker"]: row for row in probabilities}
    if len(by_ticker) != len(probabilities):
        raise ValueError("probability event tickers must be unique")
    windows = build_asset_windows(releases, _load_bars(asset_bar_path))
    release_by_id = {row.event_id: row for row in releases}
    groups: dict[tuple[str, str], list[tuple[Any, str, float]]] = defaultdict(list)
    for window in windows.windows:
        release = release_by_id[window.event_id]
        probability = by_ticker.get(release.event_ticker)
        if probability is None or probability.get("status") != "eligible":
            continue
        if probability.get("outcome") not in (None, "", release.outcome):
            raise ValueError("probability and BLS outcomes differ")
        groups[window.asset_id, window.horizon].append(
            (release.release_at, release.event_id, window.return_value)
        )

    results: dict[str, dict[str, Any]] = {}
    for asset, horizon in sorted(KEYS):
        ordered = sorted(groups[asset, horizon])
        if len({event_id for _, event_id, _ in ordered}) != len(ordered):
            raise ValueError("duplicate event for asset and horizon")
        errors: list[tuple[float, float]] = []
        for index in range(min_train, len(ordered)):
            predicted = math.fsum(value for _, _, value in ordered[:index]) / index
            actual = ordered[index][2]
            errors.append((abs(predicted - actual), abs(actual)))
        test_events = len(errors)
        status = "evaluated" if test_events >= min_test else "insufficient_test_events"
        results[f"{asset}:{horizon}"] = {
            "eligible_events": len(ordered),
            "train_start_events": min_train,
            "test_events": test_events,
            "required_test_events": min_test,
            "status": status,
            "metrics": (
                {
                    "mae": math.fsum(error for error, _ in errors) / test_events,
                    "zero_mae": math.fsum(error for _, error in errors) / test_events,
                }
                if status == "evaluated"
                else {}
            ),
        }

    report = {
        "schema_version": "cpi-asset-group-baseline-v1",
        "method": "expanding_prior_event_mean_vs_zero_return",
        "input_sha256": {
            "release_vintage_csv": hashlib.sha256(release_path.read_bytes()).hexdigest(),
            "probability_event_csv": hashlib.sha256(probability_path.read_bytes()).hexdigest(),
            "asset_minute_bar_csv": hashlib.sha256(asset_bar_path.read_bytes()).hexdigest(),
        },
        "group_results": results,
        "interpretation_boundary": "different_event_sets_not_comparable_across_groups",
        "publication_boundary": "aggregate_only_no_prices_returns_or_event_predictions",
    }
    content = (
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and output_path.read_text(encoding="utf-8") != content:
        raise ValueError("existing group report differs")
    output_path.write_text(content, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="CPI 자산·기간별 가용 사건 기준선 평가")
    parser.add_argument("--releases", type=Path, required=True)
    parser.add_argument("--probabilities", type=Path, required=True)
    parser.add_argument("--asset-bars", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    path = evaluate_groups(args.releases, args.probabilities, args.asset_bars, args.output)
    print(json.dumps({"group_report": str(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

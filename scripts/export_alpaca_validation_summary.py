from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def export_summary(
    asset_metadata_path: Path,
    panel_metadata_path: Path,
    baseline_report_path: Path,
    output_path: Path,
) -> Path:
    asset = _load(asset_metadata_path)
    panel = _load(panel_metadata_path)
    baseline = _load(baseline_report_path)
    if asset.get("schema_version") != "alpaca-etf-minute-bars-v1":
        raise ValueError("unexpected Alpaca asset metadata schema")
    if panel.get("schema_version") != "cpi-event-asset-panel-v1":
        raise ValueError("unexpected CPI asset panel schema")
    if baseline.get("input_panel_sha256") != panel.get("panel_sha256"):
        raise ValueError("baseline and panel checksums differ")

    summary = {
        "schema_version": "alpaca-ci-validation-summary-v1",
        "source": asset["source"],
        "feed": asset["feed"],
        "release_events": asset["release_events"],
        "bar_rows": asset["bar_rows"],
        "coverage_rows": asset["coverage_rows"],
        "coverage_status_counts": asset["coverage_status_counts"],
        "asset_complete_events": asset["common_events"],
        "model_common_events": panel["common_events"],
        "asset_bar_sha256": asset["bar_csv_sha256"],
        "panel_sha256": panel["panel_sha256"],
        "evaluation": {
            "status": baseline["status"],
            "method": baseline["method"],
            "train_start_events": baseline["train_start_events"],
            "test_events": baseline["test_events"],
            "required_test_events": baseline["required_test_events"],
            "metrics": baseline["metrics"],
        },
        "publication_boundary": (
            "aggregate_metrics_only_no_credentials_raw_prices_or_event_level_returns"
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Alpaca CI 검증 결과를 공개 가능한 집계 요약으로 변환"
    )
    parser.add_argument("--asset-metadata", type=Path, required=True)
    parser.add_argument("--panel-metadata", type=Path, required=True)
    parser.add_argument("--baseline-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    path = export_summary(
        args.asset_metadata,
        args.panel_metadata,
        args.baseline_report,
        args.output,
    )
    print(json.dumps({"validation_summary": str(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

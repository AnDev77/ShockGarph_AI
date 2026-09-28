from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/event_study"))

from shockgraph_analytics.paper_panel import EventAssetPanelRow  # noqa: E402
from shockgraph_analytics.price_baseline import evaluate_price_baseline  # noqa: E402


def evaluate_panel(panel_dir: Path, output_dir: Path, *, min_train: int = 5) -> Path:
    panel_path = panel_dir / "event_asset_panel.csv"
    metadata = json.loads((panel_dir / "metadata.json").read_text(encoding="utf-8"))
    panel_bytes = panel_path.read_bytes()
    panel_hash = hashlib.sha256(panel_bytes).hexdigest()
    if metadata.get("schema_version") != "cpi-event-asset-panel-v1":
        raise ValueError("unexpected asset panel schema")
    if metadata.get("panel_sha256") != panel_hash:
        raise ValueError("asset panel checksum mismatch")
    with panel_path.open(encoding="utf-8", newline="") as handle:
        rows = [EventAssetPanelRow.model_validate(row) for row in csv.DictReader(handle)]
    result = evaluate_price_baseline(
        [
            {
                "event_id": row.event_id,
                "release_at": row.release_at,
                "asset_id": row.asset_id,
                "horizon": row.horizon,
                "return_value": row.return_value,
            }
            for row in rows
        ],
        min_train=min_train,
    )
    if result["common_events"] != metadata.get("common_events"):
        raise ValueError("asset panel event count mismatch")
    result["input_panel_sha256"] = panel_hash
    result["method"] = "expanding_prior_event_mean_vs_zero_return"
    content = (
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    run_hash = hashlib.sha256(content.encode()).hexdigest()
    destination = output_dir / run_hash
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / "price_baseline_report.json"
    if path.exists() and path.read_text(encoding="utf-8") != content:
        raise ValueError("existing baseline report differs")
    if not path.exists():
        path.write_text(content, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="CPI ETF 가격 기준선의 시간순 표본 외 평가")
    parser.add_argument("--panel-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/cpi-price-baseline")
    parser.add_argument("--min-train", type=int, default=5)
    args = parser.parse_args()
    path = evaluate_panel(args.panel_dir, args.output, min_train=args.min_train)
    report = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps({"report": str(path), "status": report["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

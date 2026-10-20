"""Private A/B comparison from archived full price snapshots and timestamped indicators."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT),
    str(ROOT / "packages/event_study"),
    str(ROOT / "packages/domain"),
    str(ROOT / "packages/data_pipeline"),
    str(ROOT / "packages/risk_engine"),
]

from shockgraph_risk.daily import (  # noqa: E402
    build_snapshot_forecasts,
    evaluate_snapshot_holdout,
)
from shockgraph_risk.macro_panel import (  # noqa: E402
    MarketIndicatorObservation,
    build_macro_risk_panel,
)
from shockgraph_risk.traditional_model import evaluate_traditional_holdout  # noqa: E402

from scripts.evaluate_snapshot_holdout import load_snapshot_manifest  # noqa: E402

_FIELDS = ("name", "source", "observed_at", "available_at", "value")


def load_indicators(path: Path) -> tuple[tuple[MarketIndicatorObservation, ...], str]:
    """Hash the private source file and require explicit UTC observation/availability times."""
    try:
        contents = path.read_bytes()
        reader = csv.DictReader(io.StringIO(contents.decode("utf-8-sig"), newline=""))
        if reader.fieldnames != list(_FIELDS):
            raise ValueError("indicator CSV needs name,source,observed_at,available_at,value")
        file_hash = hashlib.sha256(contents).hexdigest()
        rows = []
        for item in reader:
            if None in item or any(item[name] is None or not item[name] for name in _FIELDS):
                raise ValueError("indicator CSV has an incomplete row")
            value = float(item["value"])
            if not math.isfinite(value):
                raise ValueError("indicator value must be finite")
            rows.append(MarketIndicatorObservation(
                name=item["name"], source=item["source"],
                observed_at=datetime.fromisoformat(item["observed_at"]),
                available_at=datetime.fromisoformat(item["available_at"]),
                value=value, raw_hash=file_hash,
            ))
    except (OSError, UnicodeDecodeError, csv.Error, KeyError) as error:
        raise ValueError("indicator CSV could not be read") from error
    if not rows:
        raise ValueError("indicator CSV must contain observations")
    return tuple(rows), file_hash


def run_traditional_manifest(
    manifest_path: Path, indicator_path: Path, raw_root: Path,
    *, indicator_names: tuple[str, ...] = ("DGS10",),
    max_indicator_age: timedelta = timedelta(days=5),
) -> dict[str, Any]:
    inputs = load_snapshot_manifest(manifest_path, raw_root)
    indicators, indicator_hash = load_indicators(indicator_path)
    if not indicator_names or len(set(indicator_names)) != len(indicator_names):
        raise ValueError("indicator names must be nonempty and unique")
    if max_indicator_age <= timedelta(0):
        raise ValueError("indicator age limit must be positive")
    baseline = evaluate_snapshot_holdout(
        inputs.snapshots, inputs.sessions, inputs.prediction_times,
        holdout_start=inputs.holdout_start, evaluation_at=inputs.evaluation_at,
    )
    compared = []
    for horizon_report in baseline.horizons:
        horizon = horizon_report.horizon
        if horizon_report.status == "blocked":
            compared.append({"horizon": horizon, "status": "blocked",
                             "reason": horizon_report.reason, "metrics": None})
            continue
        forecasts = build_snapshot_forecasts(
            inputs.snapshots, inputs.sessions, inputs.prediction_times, horizon=horizon
        )
        panel = build_macro_risk_panel(
            forecasts, indicators, [], [], required_indicators=indicator_names,
            max_indicator_age=max_indicator_age,
            max_probability_age=timedelta(days=1), max_release_lead=timedelta(days=1),
            include_probability_research=False,
        )
        result = evaluate_traditional_holdout(
            panel, inputs.snapshots, inputs.sessions, inputs.prediction_times,
            holdout_start=inputs.holdout_start, evaluation_at=inputs.evaluation_at,
            indicator_names=indicator_names,
        )
        compared.append({"horizon": horizon, "coverage": asdict(panel.coverage),
                         "metrics": asdict(result)})
    return {
        "schema_version": 1,
        "status": "private_research_only",
        "manifest_sha256": inputs.manifest_sha256,
        "indicator_file_sha256": indicator_hash,
        "indicator_names": indicator_names,
        "max_indicator_age_seconds": max_indicator_age.total_seconds(),
        "holdout_start": inputs.holdout_start,
        "evaluation_at": inputs.evaluation_at,
        "price_rights_and_vintage_unverified": True,
        "indicator_release_time_and_rights_unverified": True,
        "public_performance_allowed": False,
        "horizons": compared,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="시점이 맞는 가격·전통 지표의 비공개 A/B 비교")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--indicators", type=Path, required=True)
    parser.add_argument("--indicator", action="append", default=[], help="예: DGS10; 복수 가능")
    parser.add_argument("--max-indicator-age-hours", type=float, default=120)
    parser.add_argument("--raw-root", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--output", type=Path, help="비공개 JSON 출력 경로, 생략하면 표준 출력")
    args = parser.parse_args(argv)
    try:
        names = tuple(args.indicator) if args.indicator else ("DGS10",)
        report = run_traditional_manifest(
            args.manifest, args.indicators, args.raw_root, indicator_names=names,
            max_indicator_age=timedelta(hours=args.max_indicator_age_hours),
        )
        encoded = json.dumps(report, ensure_ascii=False, indent=2,
                             default=lambda value: value.isoformat()
                             if isinstance(value, date | datetime) else str(value)) + "\n"
        if args.output is None:
            print(encoded, end="")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as output:
                output.write(encoded)
    except (OSError, ValueError, OverflowError) as error:
        reason = (str(error) if isinstance(error, ValueError)
                  else "input or output could not be used")
        print(json.dumps({"status": "invalid_input", "reason": reason}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

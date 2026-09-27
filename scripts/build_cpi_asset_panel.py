from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/event_study"))

from shockgraph_analytics.paper_panel import (  # noqa: E402
    AssetMinuteBar,
    CpiReleaseVintage,
    assemble_event_asset_panel,
    build_asset_windows,
)

SCHEMA_VERSION = "cpi-event-asset-panel-v1"
PANEL_FIELDS = (
    "event_id",
    "event_ticker",
    "reference_month",
    "release_at",
    "actual_mom_first",
    "threshold",
    "outcome",
    "market_ticker",
    "quote_end_at",
    "probability_yes",
    "spread",
    "asset_id",
    "horizon",
    "start_at",
    "end_at",
    "start_price",
    "end_price",
    "return_value",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"input CSV is empty: {path.name}")
    return rows


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError("boolean CSV values must be true or false")
    return normalized == "true"


def _load_releases(path: Path) -> list[CpiReleaseVintage]:
    return [
        CpiReleaseVintage.model_validate(
            {
                "event_id": row["event_id"],
                "event_ticker": row["event_ticker"],
                "reference_month": date.fromisoformat(row["reference_month"]),
                "release_at": _parse_datetime(row["release_at"]),
                "actual_mom_first": float(row["actual_mom_first"]),
                "threshold": float(row["threshold"]),
                "outcome": row["bls_outcome"],
                "source_url": row["source_url"],
                "raw_hash": row["raw_hash"],
            }
        )
        for row in _read_csv(path)
    ]


def _load_bars(path: Path) -> list[AssetMinuteBar]:
    return [
        AssetMinuteBar.model_validate(
            {
                "asset_id": row["asset_id"],
                "price_at": _parse_datetime(row["price_at"]),
                "available_at": _parse_datetime(row["available_at"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "extended_hours": _parse_bool(row["extended_hours"]),
                "raw_hash": row["raw_hash"],
            }
        )
        for row in _read_csv(path)
    ]


def _write_immutable(path: Path, content: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError(f"existing panel artifact differs: {path.name}")
        return
    path.write_text(content, encoding="utf-8")


def build_panel_dataset(
    release_path: Path,
    probability_path: Path,
    asset_bar_path: Path,
    output_dir: Path,
    *,
    horizons: dict[str, int] | None = None,
) -> Path:
    horizon_minutes = horizons or {"m5": 5, "m30": 30}
    if any(minutes <= 0 for minutes in horizon_minutes.values()):
        raise ValueError("horizon minutes must be positive")
    input_hashes = {
        "release_vintage_csv": _sha256(release_path),
        "probability_event_csv": _sha256(probability_path),
        "asset_minute_bar_csv": _sha256(asset_bar_path),
    }
    identity = json.dumps(
        {"schema_version": SCHEMA_VERSION, "inputs": input_hashes, "horizons": horizon_minutes},
        sort_keys=True,
        separators=(",", ":"),
    )
    run_id = hashlib.sha256(identity.encode()).hexdigest()
    destination = output_dir / run_id
    destination.mkdir(parents=True, exist_ok=True)

    releases = _load_releases(release_path)
    probabilities: list[dict[str, Any]] = _read_csv(probability_path)
    bars = _load_bars(asset_bar_path)
    window_result = build_asset_windows(
        releases,
        bars,
        horizons={name: timedelta(minutes=minutes) for name, minutes in horizon_minutes.items()},
    )
    panel = assemble_event_asset_panel(probabilities, releases, window_result)

    csv_buffer = io.StringIO(newline="")
    fields: list[str] = list(PANEL_FIELDS)
    writer: csv.DictWriter[str] = csv.DictWriter(csv_buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in panel.rows:
        writer.writerow(row.model_dump(mode="json"))
    panel_content = csv_buffer.getvalue()
    _write_immutable(destination / "event_asset_panel.csv", panel_content)

    coverage_content = (
        json.dumps({"coverage": panel.coverage}, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    )
    _write_immutable(destination / "coverage.json", coverage_content)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "input_sha256": input_hashes,
        "horizons_minutes": horizon_minutes,
        "release_events": len(releases),
        "asset_bars": len(bars),
        "common_events": len(panel.common_event_ids),
        "common_event_ids": panel.common_event_ids,
        "panel_rows": len(panel.rows),
        "coverage_rows": len(panel.coverage),
        "panel_sha256": hashlib.sha256(panel_content.encode()).hexdigest(),
        "coverage_sha256": hashlib.sha256(coverage_content.encode()).hexdigest(),
    }
    metadata_content = json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    _write_immutable(destination / "metadata.json", metadata_content)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="CPI 확률·BLS 최초 발표·ETF 분봉 사건 패널 생성")
    parser.add_argument("--releases", type=Path, required=True)
    parser.add_argument("--probabilities", type=Path, required=True)
    parser.add_argument("--asset-bars", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/cpi-asset-panel")
    args = parser.parse_args()
    destination = build_panel_dataset(
        args.releases,
        args.probabilities,
        args.asset_bars,
        args.output,
    )
    print(json.dumps({"asset_panel": str(destination)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

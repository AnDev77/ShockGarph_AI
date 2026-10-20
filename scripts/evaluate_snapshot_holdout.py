from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "packages/domain"),
    str(ROOT / "packages/data_pipeline"),
    str(ROOT / "packages/risk_engine"),
]

from shockgraph_data_pipeline.daily_price_import import import_daily_prices  # noqa: E402
from shockgraph_data_pipeline.market_calendar import (  # noqa: E402
    NASDAQ_2026_SOURCE,
    NASDAQ_2026_VERSION,
    nasdaq_2026_sessions,
)
from shockgraph_data_pipeline.raw_store import ImmutableRawStore  # noqa: E402
from shockgraph_risk.daily import PriceSnapshot, evaluate_snapshot_holdout  # noqa: E402


def _object(value: object, fields: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{name} must contain exactly {', '.join(sorted(fields))}")
    return value


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _iso(value: date | datetime) -> str:
    return value.isoformat()


@dataclass(frozen=True, slots=True)
class LoadedSnapshotManifest:
    manifest_sha256: str
    sessions: tuple[date, ...]
    prediction_times: dict[date, datetime]
    snapshots: tuple[PriceSnapshot, ...]
    holdout_start: datetime
    evaluation_at: datetime
    provenance: tuple[dict[str, Any], ...]


def load_snapshot_manifest(manifest_path: Path, raw_root: Path) -> LoadedSnapshotManifest:
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as error:
        raise ValueError("manifest could not be read") from error
    try:
        data = _object(
            json.loads(manifest_bytes),
            {"schema_version", "source", "start", "end", "holdout_start", "evaluation_at",
             "prediction_delay_minutes", "snapshots"},
            "manifest",
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("manifest must be UTF-8 JSON") from error
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("unsupported manifest schema_version")
    source = _string(data["source"], "source")
    start = date.fromisoformat(_string(data["start"], "start"))
    end = date.fromisoformat(_string(data["end"], "end"))
    holdout_date = date.fromisoformat(_string(data["holdout_start"], "holdout_start"))
    evaluation_at = datetime.fromisoformat(_string(data["evaluation_at"], "evaluation_at"))
    delay = data["prediction_delay_minutes"]
    if type(delay) is not int or not 0 < delay <= 1440:
        raise ValueError("prediction_delay_minutes must be an integer from 1 to 1440")
    entries = data["snapshots"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("snapshots must be a nonempty list")
    sessions = nasdaq_2026_sessions(start, end)
    prediction_times = {
        session.session_date: session.close_at + timedelta(minutes=delay) for session in sessions
    }
    if holdout_date not in prediction_times:
        raise ValueError("holdout_start must be a scheduled session in the range")

    store = ImmutableRawStore(raw_root)
    snapshots = []
    provenance = []
    for number, entry in enumerate(entries, start=1):
        row = _object(entry, {"path", "captured_at", "end"}, f"snapshot {number}")
        file = manifest_path.parent / _string(row["path"], "path")
        captured_at = datetime.fromisoformat(_string(row["captured_at"], "captured_at"))
        snapshot_end = date.fromisoformat(_string(row["end"], "end"))
        if snapshot_end not in prediction_times:
            raise ValueError(f"snapshot {number}: end is not a scheduled session in the range")
        try:
            contents = file.read_bytes()
        except OSError as error:
            raise ValueError(f"snapshot {number}: file could not be read") from error
        imported = import_daily_prices(
            contents, store=store, source=source, captured_at=captured_at,
            start=start, end=snapshot_end, prediction_delay=timedelta(minutes=delay),
            full_snapshot=True,
        )
        if not imported.quality.structurally_ready:
            raise ValueError(f"snapshot {number}: incomplete or invalid calendar coverage")
        snapshots.append(PriceSnapshot(imported.captured_at, imported.prices))
        provenance.append({
            "captured_at": imported.captured_at.isoformat(),
            "file_sha256": imported.quality.file_sha256,
            "raw_payload_hash": imported.quality.raw_payload_hash,
            "session_count": len(imported.prices),
        })

    return LoadedSnapshotManifest(
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        sessions=tuple(prediction_times), prediction_times=prediction_times,
        snapshots=tuple(snapshots), holdout_start=prediction_times[holdout_date],
        evaluation_at=evaluation_at, provenance=tuple(provenance),
    )


def run_manifest(manifest_path: Path, raw_root: Path) -> dict[str, Any]:
    inputs = load_snapshot_manifest(manifest_path, raw_root)
    report = evaluate_snapshot_holdout(
        inputs.snapshots, inputs.sessions, inputs.prediction_times,
        holdout_start=inputs.holdout_start, evaluation_at=inputs.evaluation_at,
    )
    return {
        "manifest_sha256": inputs.manifest_sha256,
        "calendar_source": NASDAQ_2026_SOURCE,
        "calendar_version": NASDAQ_2026_VERSION,
        "snapshot_provenance": inputs.provenance,
        "report": asdict(report),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="보관된 TLT 수정가격의 비공개 5·20일 평가")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--output", type=Path, help="비공개 JSON 출력 경로, 생략하면 표준 출력")
    args = parser.parse_args(argv)
    try:
        report = run_manifest(args.manifest, args.raw_root)
        encoded = json.dumps(report, ensure_ascii=False, indent=2, default=_iso) + "\n"
        if args.output is None:
            print(encoded, end="")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as output:
                output.write(encoded)
    except (OSError, ValueError) as error:
        # Do not echo local source paths or proprietary price rows on failure.
        reason = str(error) if isinstance(error, ValueError) else "output could not be written"
        print(json.dumps({"status": "invalid_input", "reason": reason}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

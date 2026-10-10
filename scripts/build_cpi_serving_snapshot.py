"""원본 위치를 감사하고, 허용된 오프라인 자료를 API 서비스 스냅샷으로 변환한다."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/event_study"))

from shockgraph_analytics.connection import (  # noqa: E402
    INPUT_NAMES,
    AuthorizationRecord,
    ConnectionAudit,
    InputState,
    ServingManifest,
    blocker,
)
from shockgraph_analytics.cpi_distribution import ConsensusVintage, ThresholdQuote  # noqa: E402
from shockgraph_analytics.paper_panel import AssetMinuteBar  # noqa: E402
from shockgraph_analytics.serving import (  # noqa: E402
    ServingRelease,
    build_serving_dataset,
    demo_inputs,
)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def write_immutable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError("content-addressed artifact differs")
    else:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)


def inspect_inputs(
    manifest_path: Path,
    checked_at: datetime,
) -> tuple[ServingManifest | None, dict[str, Path], ConnectionAudit, str | None]:
    inputs = [InputState(name=name, status="missing") for name in INPUT_NAMES]
    inputs.append(InputState(name="authorization_record", status="missing"))
    audit = ConnectionAudit(
        checked_at=checked_at,
        source_kind="licensed_historical",
        status="blocked",
        inputs=inputs,
        blockers=[
            blocker("manifest_missing"),
            *[blocker(f"{name}_missing") for name in INPUT_NAMES],
            blocker("authorization_missing"),
        ],
    )
    if not manifest_path.is_file():
        return None, {}, audit, None
    try:
        manifest = ServingManifest.model_validate_json(manifest_path.read_bytes())
    except (OSError, ValueError):
        return None, {}, audit.model_copy(update={"blockers": [blocker("manifest_invalid")]}), None
    paths = {name: manifest_path.parent / getattr(manifest, name) for name in INPUT_NAMES}
    states = [
        InputState.model_validate(
            {"name": name, "status": "present" if path.is_file() else "missing"}
        )
        for name, path in paths.items()
    ]
    issues = [blocker(f"{state.name}_missing") for state in states if state.status == "missing"]
    auth_hash = None
    if manifest.source_kind == "licensed_historical":
        auth_path = manifest.authorization_record
        auth_path = manifest_path.parent / auth_path if auth_path is not None else None
        if auth_path is None or not auth_path.is_file():
            states.append(InputState(name="authorization_record", status="missing"))
            issues.append(blocker("authorization_missing"))
        else:
            try:
                evidence = auth_path.read_bytes()
                record = AuthorizationRecord.model_validate_json(evidence)
                if not record.covers(checked_at):
                    raise ValueError("authorization scope or validity incomplete")
                auth_hash = hashlib.sha256(evidence).hexdigest()
                states.append(InputState(name="authorization_record", status="present"))
            except (OSError, ValueError):
                states.append(InputState(name="authorization_record", status="invalid"))
                issues.append(blocker("authorization_invalid"))
    else:
        states.append(InputState(name="authorization_record", status="not_required"))
    audit = ConnectionAudit(
        checked_at=checked_at,
        source_kind=manifest.source_kind,
        status="blocked" if issues else "inputs_present",
        inputs=states,
        blockers=issues,
    )
    return manifest, paths, audit, auth_hash


def csv_rows(content: bytes) -> list[dict[str, str]]:
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    if not rows:
        raise ValueError("empty CSV")
    return rows


def load_quotes(content: bytes, manifest: ServingManifest) -> list[ThresholdQuote]:
    value = json.loads(content)
    if isinstance(value, list):
        return [ThresholdQuote.model_validate(row) for row in value]
    if not isinstance(value, dict) or (
        value.get("schema_version") != "kalshi-cpi-threshold-curve-v1"
        or value.get("event_ticker") != manifest.target_event_id
        or datetime.fromisoformat(value["as_of"].replace("Z", "+00:00")) != manifest.as_of
        or value.get("contract_definition")
        != "single_decimal_cpi_mom_strictly_greater_percentage_point"
    ):
        raise ValueError("original target quotes required; aggregate summary insufficient")
    return [
        ThresholdQuote(
            event_id=manifest.target_event_id,
            market_ticker=row["market_ticker"],
            threshold=row["threshold"],
            probability_above=row["probability_above"],
            observed_at=row["quote_end_at"],
            available_at=row["quote_end_at"],
            spread=row["spread"],
            raw_hash=row["raw_hash"],
        )
        for row in value["quotes"]
        if row["status"] == "eligible"
    ]


def build_snapshot(
    manifest_path: Path,
    output: Path,
    *,
    check_only: bool = False,
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    manifest, paths, audit, auth_hash = inspect_inputs(
        manifest_path, checked_at or datetime.now(UTC)
    )
    snapshot_path = None
    if manifest is not None and not audit.blockers and not check_only:
        try:
            # Financial inputs are read only after the required usage record passes the audit.
            contents = {name: path.read_bytes() for name, path in paths.items()}
            releases = [
                ServingRelease.model_validate(
                    {
                        name: row[name]
                        for name in (
                            "event_id",
                            "event_ticker",
                            "release_at",
                            "actual_mom_first",
                            "source_url",
                            "raw_hash",
                        )
                    }
                )
                for row in csv_rows(contents["release_csv"])
            ]
            bars = []
            for row in csv_rows(contents["asset_bar_csv"]):
                if row["extended_hours"].lower() not in ("true", "false"):
                    raise ValueError("extended-hours flag must be true or false")
                bars.append(
                    AssetMinuteBar.model_validate(
                        {
                            **{
                                name: row[name]
                                for name in (
                                    "asset_id",
                                    "price_at",
                                    "available_at",
                                    "open",
                                    "high",
                                    "low",
                                    "close",
                                    "volume",
                                    "raw_hash",
                                )
                            },
                            "extended_hours": row["extended_hours"].lower() == "true",
                        }
                    )
                )
            consensuses = [
                ConsensusVintage.model_validate(row)
                for row in json.loads(contents["consensus_json"])
            ]
            dataset, coverage = build_serving_dataset(
                releases=releases,
                bars=bars,
                consensuses=consensuses,
                quotes=load_quotes(contents["target_quotes_json"], manifest),
                target_event_id=manifest.target_event_id,
                as_of=manifest.as_of,
                release_at=manifest.release_at,
                source_kind=manifest.source_kind,
                source_reference=manifest.source_reference,
                label_timing_policy=manifest.label_timing_policy,
                authorization_reference=f"sha256:{auth_hash}" if auth_hash else None,
            )
            content = canonical(dataset.model_dump(mode="json"))
            digest = hashlib.sha256(content.encode()).hexdigest()
            destination = output / "snapshots" / digest
            snapshot_path = destination / "scenario_dataset.json"
            metadata = {
                "schema_version": "cpi-serving-lineage-v1",
                "source_kind": manifest.source_kind,
                "input_sha256": {
                    name: hashlib.sha256(value).hexdigest() for name, value in contents.items()
                },
                "normalized_manifest_sha256": hashlib.sha256(
                    canonical(manifest.model_dump(mode="json")).encode()
                ).hexdigest(),
                "authorization_record_sha256": auth_hash,
                "label_timing_policy": manifest.label_timing_policy,
                "quote_timing_policy": "declared_quote_availability_or_candle_end_proxy",
                "price_definition": "normalized_minute_close_at_release_minus_1_and_plus_5_or_30",
                "snapshot_sha256": digest,
            }
            write_immutable(snapshot_path, content)
            # Equal numeric snapshots can have different source-file lineage.
            lineage = canonical({"metadata": metadata, "coverage": coverage})
            lineage_digest = hashlib.sha256(lineage.encode()).hexdigest()
            write_immutable(output / "lineage" / lineage_digest / "report.json", lineage)
            audit = audit.model_copy(
                update={
                    "status": "snapshot_built",
                    "snapshot_sha256": digest,
                    "event_counts": dict(Counter(row["status"] for row in coverage)),
                }
            )
        except (OSError, ValueError, KeyError, TypeError):
            audit = audit.model_copy(
                update={"status": "blocked", "blockers": [blocker("input_invalid")]}
            )
            snapshot_path = None
    audit_content = canonical(audit.model_dump(mode="json"))
    audit_digest = hashlib.sha256(audit_content.encode()).hexdigest()
    report_path = output / "readiness" / audit_digest / "report.json"
    write_immutable(report_path, audit_content)
    return {
        "status": audit.status,
        "readiness_report": str(report_path.resolve()),
        "snapshot": str(snapshot_path.resolve()) if snapshot_path else None,
        "blocker_codes": [b.code for b in audit.blockers],
    }


def create_demo_manifest(output: Path) -> Path:
    inputs = demo_inputs()
    root = output / "synthetic-inputs"
    root.mkdir(parents=True, exist_ok=True)
    for name, rows in (("releases.csv", inputs["releases"]), ("bars.csv", inputs["bars"])):
        objects = [r.model_dump(mode="json") for r in rows]
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=list(objects[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(objects)
        write_immutable(root / name, buffer.getvalue())
    for name, rows in (
        ("consensus.json", inputs["consensuses"]),
        ("quotes.json", inputs["quotes"]),
    ):
        write_immutable(root / name, canonical([r.model_dump(mode="json") for r in rows]))
    manifest = ServingManifest(
        source_kind="synthetic",
        source_reference=inputs["source_reference"],
        target_event_id=inputs["target_event_id"],
        as_of=inputs["as_of"],
        release_at=inputs["release_at"],
        label_timing_policy=inputs["label_timing_policy"],
        release_csv=Path("releases.csv"),
        asset_bar_csv=Path("bars.csv"),
        consensus_json=Path("consensus.json"),
        target_quotes_json=Path("quotes.json"),
    )
    path = root / "manifest.json"
    write_immutable(path, canonical(manifest.model_dump(mode="json")))
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="CPI 서비스 입력 연결 감사·오프라인 스냅샷 생성")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/cpi-serving")
    args = parser.parse_args()
    if args.demo and args.manifest:
        parser.error("--demo와 --manifest는 동시에 지정할 수 없습니다")
    path = create_demo_manifest(args.output) if args.demo else args.manifest
    if path is None:
        path = ROOT / "data/clean/cpi-serving-manifest.json"
    result = build_snapshot(path, args.output, check_only=args.check_only)
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] == "blocked" and not args.check_only:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

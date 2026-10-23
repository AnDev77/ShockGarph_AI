"""Archive a verified Alpaca capture in a private, write-once S3 bucket.

Forecasts are stored only if archiving finishes before the next outcome close.
No source prices or forecasts are printed to public workflow logs.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import importlib
import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages/domain"),
                str(ROOT / "packages/data_pipeline"), str(ROOT / "packages/risk_engine")]

from shockgraph_data_pipeline.kalshi_contract import payload_sha256  # noqa: E402
from shockgraph_data_pipeline.market_calendar import nasdaq_sessions  # noqa: E402
from shockgraph_risk.forward_risk_capture import build_forward_risk_record  # noqa: E402

from scripts.analyze_alpaca_history import _read_symbol  # noqa: E402

_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_PREFIX = re.compile(r"^[a-zA-Z0-9/_-]+$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


class S3Like(Protocol):
    def put_object(self, *, Bucket: str, Key: str, Body: bytes,
                   Metadata: dict[str, str], ServerSideEncryption: str,
                   IfNoneMatch: str) -> Any: ...
    def head_object(self, *, Bucket: str, Key: str) -> Mapping[str, Any]: ...
    def get_object(self, *, Bucket: str, Key: str) -> Mapping[str, Any]: ...


def _encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True,
                       separators=(",", ":"), default=lambda item: item.isoformat()) + "\n"
            ).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _raw_bytes(path_value: object, *, root: Path, expected_hash: object,
               file_sha: object, source: str) -> tuple[bytes, str]:
    if not isinstance(path_value, str):
        raise ValueError("raw artifact path is missing")
    path = Path(path_value).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("raw artifact is outside private raw root")
    data = path.read_bytes()
    try:
        envelope = json.loads(data)
        if _encoded(envelope) != data:
            raise ValueError("raw artifact bytes differ from immutable envelope")
        metadata, payload = envelope["metadata"], envelope["payload"]
        if (metadata["source"] != source or metadata["payload_sha256"] != expected_hash
                or payload_sha256(payload) != expected_hash
                or payload["file_sha256"] != file_sha):
            raise ValueError("raw artifact hash differs from capture manifest")
        key = "body_base64" if source == "alpaca" else "content_base64"
        decoded = base64.b64decode(payload[key], validate=True)
        if _digest(decoded) != file_sha:
            raise ValueError("raw artifact file bytes differ from capture manifest")
    except (TypeError, KeyError, json.JSONDecodeError, binascii.Error) as error:
        raise ValueError("raw artifact envelope is invalid") from error
    return data, path.relative_to(root).as_posix()


def _write_once(s3: S3Like, bucket: str, key: str, data: bytes) -> bool:
    digest = _digest(data)
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=data,
                      Metadata={"sha256": digest}, ServerSideEncryption="AES256",
                      IfNoneMatch="*")
        created = True
    except Exception as error:
        response = getattr(error, "response", None)
        code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
        if code not in ("412", "PreconditionFailed"):
            raise
        created = False
    head = s3.head_object(Bucket=bucket, Key=key)
    if (head.get("ContentLength") != len(data)
            or head.get("Metadata", {}).get("sha256") != digest):
        raise ValueError("immutable object collision in private archive")
    actual = s3.get_object(Bucket=bucket, Key=key)["Body"].read(len(data) + 1)
    if actual != data:
        raise ValueError("immutable object collision in private archive")
    return created


def archive_capture(
    manifest_path: Path,
    *,
    raw_root: Path,
    s3: S3Like,
    bucket: str,
    prefix: str,
    prediction_at: datetime,
    receipt_clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Validate all local bytes before any private upload; retry is write-once."""
    if not _BUCKET.fullmatch(bucket) or not _PREFIX.fullmatch(prefix) or ".." in prefix:
        raise ValueError("private bucket and archive prefix are required")
    if prediction_at.tzinfo is None or prediction_at.utcoffset() != timedelta(0):
        raise ValueError("prediction_at must be UTC")
    prediction_at = prediction_at.astimezone(UTC)
    raw_root = raw_root.resolve()
    manifest_path = manifest_path.resolve()
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if (manifest.get("status") != "archived_research_only"
            or manifest.get("redistribution_rights_verified") is not False
            or not isinstance(manifest.get("prices"), list)
            or len(manifest["prices"]) != 2
            or {item.get("symbol") for item in manifest["prices"]} != {"TLT", "SPY"}):
        raise ValueError("expected a private TLT/SPY research manifest")
    archive_prefix = f"{prefix.strip('/')}/captures/{_digest(manifest_bytes)}"
    candidates: list[tuple[str, bytes]] = []
    captured_series = []
    for entry in manifest["prices"]:
        symbol = entry["symbol"]
        prices, _ = _read_symbol(entry, manifest_path.parent.parent)
        path = Path(entry["snapshot_path"]).resolve()
        csv_bytes = path.read_bytes()
        candidates.append((f"{archive_prefix}/{symbol}/prices.csv", csv_bytes))
        raw_paths = entry.get("source_raw_artifact_paths")
        raw_hashes = entry.get("source_raw_payload_hashes")
        response_hashes = entry.get("source_response_sha256")
        if (not isinstance(raw_paths, list) or not raw_paths
                or not isinstance(raw_hashes, list) or not isinstance(response_hashes, list)
                or len(raw_paths) != len(raw_hashes) or len(raw_paths) != len(response_hashes)
                or any(not isinstance(value, str) or not _SHA.fullmatch(value)
                       for value in (*raw_hashes, *response_hashes))):
            raise ValueError("raw artifact list is incomplete")
        for raw_path, raw_hash, file_sha in zip(raw_paths, raw_hashes, response_hashes,
                                                 strict=True):
            body, relative = _raw_bytes(raw_path, root=raw_root / "alpaca",
                                        expected_hash=raw_hash, file_sha=file_sha,
                                        source="alpaca")
            candidates.append((f"{archive_prefix}/raw/alpaca/{relative}", body))
        normalized, relative = _raw_bytes(
            entry.get("normalized_raw_artifact_path"), root=raw_root / "alpaca-sip",
            expected_hash=entry.get("normalized_raw_payload_hash"),
            file_sha=entry["normalized_csv_sha256"], source="alpaca-sip",
        )
        candidates.append((f"{archive_prefix}/raw/alpaca-sip/{relative}", normalized))
        capture_time = datetime.fromisoformat(entry["capture"])
        if prediction_at <= capture_time:
            raise ValueError("prediction_at must follow actual price capture")
        captured_series.append((symbol, prices, capture_time, entry["normalized_csv_sha256"]))
    candidates.append((f"{archive_prefix}/manifest.json", manifest_bytes))
    # First persist source bytes; this output cannot be called a pre-close forecast
    # unless the archive receipt itself is also written before the next close.
    created = sum(_write_once(s3, bucket, key, body) for key, body in candidates)
    receipt = (receipt_clock or (lambda: datetime.now(UTC)))()
    if receipt.tzinfo is None or receipt.utcoffset() != timedelta(0):
        raise ValueError("archive receipt clock must be UTC")
    receipt = receipt.astimezone(UTC)
    if receipt < prediction_at:
        raise ValueError("archive receipt precedes archive start")
    forward = []
    reviewed_calendar = True
    for symbol, prices, capture_time, snapshot_hash in captured_series:
        future = nasdaq_sessions(prices[-1].session_date + timedelta(days=1),
                                 datetime(2026, 12, 31, tzinfo=UTC).date())
        if len(future) < 20:
            reviewed_calendar = False
        # The Actions job has a 20-minute timeout. Keep an additional hour
        # between the archive receipt and the first outcome close.
        elif receipt <= future[0].close_at - timedelta(hours=1):
            record = build_forward_risk_record(
                symbol, prices, source_snapshot_sha256=snapshot_hash,
                source_captured_at=capture_time, prediction_at=receipt,
            )
            forward.append(asdict(record))
    status = ("forward_forecasts_archived" if len(forward) == 2 else
              "snapshot_only_reviewed_calendar_exhausted" if not reviewed_calendar else
              "snapshot_only_preclose_gate_failed")
    index = {
        "status": status, "schema_version": 1,
        "archive_manifest_sha256": _digest(manifest_bytes),
        "prediction_at": receipt.isoformat() if forward else None,
        "archive_receipt_at": receipt.isoformat(),
        "source_object_count": len(candidates),
        "source_objects": [{"key": key, "sha256": _digest(data)} for key, data in candidates],
        "forecasts": forward,
        "historical_price_vintages_verified": False,
        "public_performance_allowed": False,
    }
    index_key = f"{archive_prefix}/records/{receipt:%Y%m%dT%H%M%S.%fZ}.json"
    created += _write_once(s3, bucket, index_key, _encoded(index))
    return {"status": status, "forecast_count": len(forward),
            "created_object_count": created, "index_key": index_key,
            "public_performance_allowed": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alpaca 가격과 사전 위험 예측을 비공개 보관")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--prefix", default="shockgraph-research")
    args = parser.parse_args(argv)
    bucket = os.environ.get("SHOCKGRAPH_PRIVATE_BUCKET", "")
    if not bucket:
        print(json.dumps({"status": "private_archive_not_configured"}))
        return 2
    try:
        boto3 = importlib.import_module("boto3")
        client = boto3.client("s3")
        block = client.get_public_access_block(Bucket=bucket)["PublicAccessBlockConfiguration"]
        if not all(block.get(name) is True for name in (
            "BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy",
            "RestrictPublicBuckets",
        )):
            raise ValueError("bucket public access block is required")
        report = archive_capture(
            args.manifest, raw_root=args.raw_root, s3=client,
            bucket=bucket, prefix=args.prefix, prediction_at=datetime.now(UTC),
        )
    except (OSError, ValueError, ImportError, TypeError, KeyError):
        print(json.dumps({"status": "private_archive_failed"}))
        return 2
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

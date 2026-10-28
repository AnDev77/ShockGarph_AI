"""Store a QQQ research capture in R2 without creating a forward forecast."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.analyze_alpaca_history import _read_symbol  # noqa: E402
from scripts.archive_forward_capture import (  # noqa: E402
    S3Like,
    _digest,
    _encoded,
    _raw_bytes,
    _write_once,
)
from scripts.private_r2 import bucket_budget_guard, configured_r2  # noqa: E402

_BUCKET = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
_PREFIX = re.compile(r"^[a-zA-Z0-9/_-]+$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


def _verified_object(s3: S3Like, bucket: str, key: str,
                     expected_sha: str | None = None) -> tuple[bytes, datetime]:
    head = s3.head_object(Bucket=bucket, Key=key)
    written = head.get("LastModified")
    size = head.get("ContentLength")
    if (not isinstance(written, datetime) or written.tzinfo is None
            or written.utcoffset() != timedelta(0)
            or not isinstance(size, int) or size < 0):
        raise ValueError("research archive metadata is invalid")
    data = s3.get_object(Bucket=bucket, Key=key)["Body"].read(size + 1)
    digest = _digest(data)
    if (len(data) != size or head.get("Metadata", {}).get("sha256") != digest
            or expected_sha is not None and expected_sha != digest):
        raise ValueError("research archive readback hash differs")
    return data, written.astimezone(UTC)


def audit_qqq_capture(s3: S3Like, *, bucket: str, index_key: str) -> dict[str, Any]:
    """Independently read back the research index and each private source byte."""
    index_bytes, index_written = _verified_object(s3, bucket, index_key)
    index = json.loads(index_bytes)
    if (not isinstance(index, dict) or index.get("schema_version") != 1
            or index.get("status") != "research_price_only"
            or index.get("symbol") != "QQQ" or index.get("forecasts") != []
            or index.get("redistribution_rights_verified") is not False
            or index.get("historical_provider_release_times_verified") is not False):
        raise ValueError("invalid QQQ research archive index")
    archive_prefix = index_key.removesuffix("/records/index.json")
    if (archive_prefix == index_key or "/qqq-captures/" not in archive_prefix
            or not _SHA.fullmatch(archive_prefix.rsplit("/", 1)[-1])):
        raise ValueError("invalid QQQ research index key")
    sources = index.get("source_objects")
    if (not isinstance(sources, list) or len(sources) != index.get("source_object_count")
            or len(sources) < 5 or not all(isinstance(item, dict) for item in sources)):
        raise ValueError("QQQ research source list is incomplete")
    seen: set[str] = set()
    latest_source = datetime.min.replace(tzinfo=UTC)
    manifest_digest = None
    for item in sources:
        key, expected = item.get("key"), item.get("sha256")
        if (not isinstance(key, str) or not key.startswith(archive_prefix + "/")
                or key in seen or not isinstance(expected, str)
                or not _SHA.fullmatch(expected)):
            raise ValueError("QQQ research source key or hash is invalid")
        seen.add(key)
        body, written = _verified_object(s3, bucket, key, expected)
        latest_source = max(latest_source, written)
        if key == archive_prefix + "/manifest.json":
            manifest_digest = expected
            manifest = json.loads(body)
            if (manifest.get("redistribution_rights_verified") is not False
                    or [row.get("symbol") for row in manifest.get("prices", [])] != ["QQQ"]):
                raise ValueError("QQQ research manifest differs from index")
    if (manifest_digest != index.get("archive_manifest_sha256")
            or archive_prefix + "/QQQ/prices.csv" not in seen
            or latest_source > index_written):
        raise ValueError("QQQ research index precedes or differs from sources")
    return {"status": "research_price_readback_verified",
            "source_object_count": len(sources), "forecast_count": 0}


def archive_qqq_capture(
    manifest_path: Path, *, raw_root: Path, s3: S3Like,
    bucket: str, prefix: str,
    budget_check: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    """Validate one QQQ manifest and all raw bytes before a write-once upload."""
    if not _BUCKET.fullmatch(bucket) or not _PREFIX.fullmatch(prefix) or ".." in prefix:
        raise ValueError("private bucket and archive prefix are required")
    raw_root = raw_root.resolve()
    manifest_path = manifest_path.resolve()
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    entries = manifest.get("prices")
    if (manifest.get("status") != "archived_research_only"
            or manifest.get("redistribution_rights_verified") is not False
            or manifest.get("historical_provider_release_times_verified") is not False
            or not isinstance(entries, list) or len(entries) != 1
            or not isinstance(entries[0], dict) or entries[0].get("symbol") != "QQQ"
            or entries[0].get("public_performance_allowed") is not False):
        raise ValueError("expected one private QQQ research manifest")
    entry = entries[0]
    _read_symbol(entry, manifest_path.parent.parent)
    archive_prefix = f"{prefix.strip('/')}/qqq-captures/{_digest(manifest_bytes)}"
    path = Path(entry["snapshot_path"]).resolve()
    candidates = [(f"{archive_prefix}/QQQ/prices.csv", path.read_bytes())]
    raw_paths = entry.get("source_raw_artifact_paths")
    raw_hashes = entry.get("source_raw_payload_hashes")
    response_hashes = entry.get("source_response_sha256")
    if (not isinstance(raw_paths, list) or not raw_paths
            or not isinstance(raw_hashes, list) or not isinstance(response_hashes, list)
            or len(raw_paths) != len(raw_hashes) or len(raw_paths) != len(response_hashes)
            or any(not isinstance(value, str) or not _SHA.fullmatch(value)
                   for value in (*raw_hashes, *response_hashes))):
        raise ValueError("QQQ raw source list is incomplete")
    for raw_path, raw_hash, file_sha in zip(raw_paths, raw_hashes, response_hashes,
                                             strict=True):
        body, relative = _raw_bytes(raw_path, root=raw_root / "alpaca",
                                    expected_hash=raw_hash, file_sha=file_sha,
                                    source="alpaca")
        candidates.append((f"{archive_prefix}/raw/alpaca/{relative}", body))
    normalized, relative = _raw_bytes(
        entry.get("normalized_raw_artifact_path"), root=raw_root / "alpaca-sip",
        expected_hash=entry.get("normalized_raw_payload_hash"),
        file_sha=entry.get("normalized_csv_sha256"), source="alpaca-sip",
    )
    candidates.extend(((f"{archive_prefix}/raw/alpaca-sip/{relative}", normalized),
                       (f"{archive_prefix}/manifest.json", manifest_bytes)))
    if budget_check is not None:
        budget_check(sum(len(body) for _, body in candidates) + 16_000)
    created = sum(_write_once(s3, bucket, key, data) for key, data in candidates)
    index = {
        "schema_version": 1, "status": "research_price_only", "symbol": "QQQ",
        "source_object_count": len(candidates),
        "source_objects": [{"key": key, "sha256": _digest(data)} for key, data in candidates],
        "archive_manifest_sha256": _digest(manifest_bytes), "forecasts": [],
        "historical_provider_release_times_verified": False,
        "redistribution_rights_verified": False,
    }
    index_key = f"{archive_prefix}/records/index.json"
    created += _write_once(s3, bucket, index_key, _encoded(index))
    return {"status": "research_price_only", "created_object_count": created,
            "source_object_count": len(candidates), "index_key": index_key}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QQQ 비공개 연구 원본 불변 보관")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--prefix", default="shockgraph-research")
    args = parser.parse_args(argv)
    try:
        client, bucket = configured_r2()
        report = archive_qqq_capture(
            args.manifest, raw_root=args.raw_root, s3=client, bucket=bucket,
            prefix=args.prefix, budget_check=bucket_budget_guard(client, bucket),
        )
        audit = audit_qqq_capture(client, bucket=bucket, index_key=report["index_key"])
    except Exception:
        print(json.dumps({"status": "private_qqq_archive_failed"}))
        return 2
    print(json.dumps({"status": audit["status"],
                      "created_object_count": report["created_object_count"],
                      "source_object_count": audit["source_object_count"],
                      "forecast_count": audit["forecast_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

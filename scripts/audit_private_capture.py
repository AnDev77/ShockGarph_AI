"""Read-only S3 audit of a private price vintage and forward risk record."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shockgraph_data_pipeline.market_calendar import nasdaq_sessions  # noqa: E402

from scripts.archive_forward_capture import audit_capture  # noqa: E402
from scripts.private_r2 import configured_r2  # noqa: E402

_INDEX = re.compile(r"^[0-9a-f]{64}/records/[0-9]{8}T[0-9]{6}\.[0-9]{6}Z\.json$")
_PREFIX = re.compile(r"^[a-zA-Z0-9/_-]+$")


def _listed_indices(client: Any, *, bucket: str, prefix: str) -> list[tuple[datetime, str]]:
    if not _PREFIX.fullmatch(prefix) or ".." in prefix:
        raise ValueError("invalid private archive prefix")
    root = prefix.strip("/") + "/captures/"
    cursor: str | None = None
    seen_tokens: set[str] = set()
    indices: list[tuple[datetime, str]] = []
    while True:
        kwargs = {"Bucket": bucket, "Prefix": root}
        if cursor is not None:
            kwargs["ContinuationToken"] = cursor
        page = client.list_objects_v2(**kwargs)
        for entry in page.get("Contents", []):
            key = entry.get("Key")
            if not isinstance(key, str) or not key.startswith(root):
                raise ValueError("archive listing contains an invalid key")
            if not _INDEX.fullmatch(key[len(root):]):
                continue
            written = entry.get("LastModified")
            if (not isinstance(written, datetime) or written.tzinfo is None
                    or written.utcoffset() != timedelta(0)):
                raise ValueError("archive listing timestamp is invalid")
            indices.append((written.astimezone(UTC), key))
        if not page.get("IsTruncated", False):
            break
        token = page.get("NextContinuationToken")
        if not isinstance(token, str) or not token or token in seen_tokens:
            raise ValueError("archive listing is incomplete")
        seen_tokens.add(token)
        cursor = token
    if not indices:
        raise ValueError("no archive index exists")
    return indices


def latest_capture(client: Any, *, bucket: str, prefix: str) -> dict[str, Any]:
    """Find the newest verified index without printing private object names."""
    indices = _listed_indices(client, bucket=bucket, prefix=prefix)
    _, key = max(indices)
    result = audit_capture(client, bucket=bucket, index_key=key)
    index = json.loads(client.get_object(Bucket=bucket, Key=key)["Body"].read())
    origins = {item.get("origin_session") for item in index["forecasts"]}
    if result["forecast_count"] and (len(origins) != 1 or None in origins):
        raise ValueError("private forecast origins differ")
    return {**result, "capture_index_count": len(indices),
            "capture_status": index["status"],
            "origin_session": next(iter(origins)) if origins else None}


def capture_inventory(client: Any, *, bucket: str, prefix: str) -> dict[str, Any]:
    """Audit every index before counting distinct prospective origin sessions."""
    indices = _listed_indices(client, bucket=bucket, prefix=prefix)
    if len(indices) > 250:
        raise ValueError("archive inventory exceeds the review limit")
    origins: set[str] = set()
    forecast_indices = 0
    snapshot_reasons = {
        "snapshot_only_preopen_gate_failed": 0,
        "snapshot_only_reviewed_calendar_exhausted": 0,
    }
    for _, key in indices:
        verified = audit_capture(client, bucket=bucket, index_key=key)
        index = json.loads(client.get_object(Bucket=bucket, Key=key)["Body"].read())
        if not verified["forecast_count"]:
            reason = index.get("status")
            if reason not in snapshot_reasons:
                raise ValueError("snapshot-only archive has an unrecognized reason")
            snapshot_reasons[reason] += 1
            continue
        days = {item.get("origin_session") for item in index["forecasts"]}
        if len(days) != 1 or None in days:
            raise ValueError("private forecast origins differ")
        origins.update(days)
        forecast_indices += 1
    return {"status": "archive_inventory_verified", "audited_index_count": len(indices),
            "forecast_index_count": forecast_indices,
            "snapshot_only_index_count": sum(snapshot_reasons.values()),
            "snapshot_only_reason_counts": snapshot_reasons,
            "unique_origin_session_count": len(origins),
            "duplicate_forecast_index_count": forecast_indices - len(origins)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="비공개 가격 빈티지 원격 재검증")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--index-key")
    target.add_argument("--latest", action="store_true")
    target.add_argument("--inventory", action="store_true")
    parser.add_argument("--expected-origin", type=date.fromisoformat,
                        help="--latest에 한해 이 거래일의 사전 예측 저장을 필수로 검사")
    parser.add_argument("--prefix", default="shockgraph-research")
    args = parser.parse_args(argv)
    if args.expected_origin is not None:
        if not args.latest:
            parser.error("--expected-origin requires --latest")
        try:
            valid_session = bool(nasdaq_sessions(args.expected_origin, args.expected_origin))
        except ValueError:
            valid_session = False
        if not valid_session:
            parser.error("--expected-origin must be a reviewed trading session")
    try:
        client, bucket = configured_r2()
    except (ValueError, ImportError):
        print(json.dumps({"status": "private_archive_not_configured"}))
        return 2
    except Exception:
        print(json.dumps({"status": "private_archive_audit_failed"}))
        return 2
    try:
        if args.inventory:
            result = capture_inventory(client, bucket=bucket, prefix=args.prefix)
        elif args.latest:
            result = latest_capture(client, bucket=bucket, prefix=args.prefix)
        else:
            result = audit_capture(client, bucket=bucket, index_key=args.index_key)
    except Exception:
        print(json.dumps({"status": "private_archive_audit_failed"}))
        return 2
    if args.expected_origin is not None:
        # A successful object read or an older forecast is not today's forecast.
        # latest_capture has already verified remote bytes and write timestamps.
        ready = (result["capture_status"] == "forward_forecasts_archived"
                 and result["forecast_count"] == 2
                 and result["origin_session"] == args.expected_origin.isoformat())
        print(json.dumps({
            "status": "prospective_capture_verified" if ready else "prospective_capture_missing",
            "expected_origin_session": args.expected_origin.isoformat(),
            "capture_status": result["capture_status"],
            "public_performance_allowed": False,
        }))
        return 0 if ready else 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

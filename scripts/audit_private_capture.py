"""Read-only S3 audit of a private price vintage and forward risk record."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.archive_forward_capture import audit_capture  # noqa: E402
from scripts.private_r2 import configured_r2  # noqa: E402

_INDEX = re.compile(r"^[0-9a-f]{64}/records/[0-9]{8}T[0-9]{6}\.[0-9]{6}Z\.json$")
_PREFIX = re.compile(r"^[a-zA-Z0-9/_-]+$")


def latest_capture(client: Any, *, bucket: str, prefix: str) -> dict[str, Any]:
    """Find the newest verified index without printing private object names."""
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
    _, key = max(indices)
    result = audit_capture(client, bucket=bucket, index_key=key)
    return {**result, "capture_index_count": len(indices)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="비공개 가격 빈티지 원격 재검증")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--index-key")
    target.add_argument("--latest", action="store_true")
    parser.add_argument("--prefix", default="shockgraph-research")
    args = parser.parse_args(argv)
    try:
        client, bucket = configured_r2()
    except (ValueError, ImportError):
        print(json.dumps({"status": "private_archive_not_configured"}))
        return 2
    except Exception:
        print(json.dumps({"status": "private_archive_audit_failed"}))
        return 2
    try:
        result = (latest_capture(client, bucket=bucket, prefix=args.prefix) if args.latest else
                  audit_capture(client, bucket=bucket, index_key=args.index_key))
    except Exception:
        print(json.dumps({"status": "private_archive_audit_failed"}))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

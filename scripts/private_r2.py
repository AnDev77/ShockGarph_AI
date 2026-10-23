"""Private Cloudflare R2 connection and conservative per-bucket storage guard."""

from __future__ import annotations

import importlib
import os
import re
from collections.abc import Callable, Mapping
from typing import Any, Protocol

MAX_CAPTURE_BYTES = 4_000_000
MAX_BUCKET_BYTES = 8_000_000_000
_ACCOUNT = re.compile(r"^[0-9a-f]{32}$")
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")


class R2Listable(Protocol):
    def list_objects_v2(self, *, Bucket: str,
                        ContinuationToken: str | None = None) -> Mapping[str, Any]: ...


def configured_r2() -> tuple[Any, str]:
    account = os.environ.get("SHOCKGRAPH_R2_ACCOUNT_ID", "")
    bucket = os.environ.get("SHOCKGRAPH_R2_BUCKET", "")
    key = os.environ.get("SHOCKGRAPH_R2_ACCESS_KEY_ID", "")
    secret = os.environ.get("SHOCKGRAPH_R2_SECRET_ACCESS_KEY", "")
    if not (_ACCOUNT.fullmatch(account) and _BUCKET.fullmatch(bucket) and key and secret):
        raise ValueError("private R2 configuration is incomplete")
    client = importlib.import_module("boto3").client(
        "s3", endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        region_name="auto", aws_access_key_id=key, aws_secret_access_key=secret,
    )
    return client, bucket


def bucket_budget_guard(s3: R2Listable, bucket: str) -> Callable[[int], None]:
    """Reject a capture before writing when this dedicated bucket approaches 8 GB."""
    def check(planned_bytes: int) -> None:
        if planned_bytes <= 0 or planned_bytes > MAX_CAPTURE_BYTES:
            raise ValueError("private R2 capture exceeds the per-run budget")
        total = 0
        cursor: str | None = None
        while True:
            page = (s3.list_objects_v2(Bucket=bucket) if cursor is None else
                    s3.list_objects_v2(Bucket=bucket, ContinuationToken=cursor))
            for item in page.get("Contents", []):
                size = item.get("Size")
                if not isinstance(size, int) or size < 0:
                    raise ValueError("private R2 object size is invalid")
                total += size
                if total + planned_bytes > MAX_BUCKET_BYTES:
                    raise ValueError("private R2 bucket budget would be exceeded")
            if not page.get("IsTruncated", False):
                break
            next_cursor = page.get("NextContinuationToken")
            if not isinstance(next_cursor, str) or not next_cursor or next_cursor == cursor:
                raise ValueError("private R2 bucket listing is incomplete")
            cursor = next_cursor
    return check

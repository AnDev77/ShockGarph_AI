from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

from shockgraph_data_pipeline.ports import ObjectReference

_BUCKET_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SEGMENT_PATTERN = re.compile(r"[^a-zA-Z0-9._=-]+")


class ObjectIntegrityError(RuntimeError):
    """Raised when an immutable object key already contains different bytes."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def build_object_key(
    *,
    namespace: str,
    source: str,
    observed_date: date,
    payload_sha256: str,
    suffix: str = "json",
) -> str:
    if not _HASH_PATTERN.fullmatch(payload_sha256):
        raise ValueError("payload_sha256 must be 64 lowercase hex characters")
    segments = [namespace, source]
    cleaned = [_SEGMENT_PATTERN.sub("_", segment).strip("._/") for segment in segments]
    if any(not segment for segment in cleaned):
        raise ValueError("object key segments cannot be empty")
    clean_suffix = _SEGMENT_PATTERN.sub("", suffix).lstrip(".")
    if not clean_suffix:
        raise ValueError("suffix is required")
    return str(
        PurePosixPath(
            *cleaned,
            f"year={observed_date:%Y}",
            f"month={observed_date:%m}",
            f"day={observed_date:%d}",
            f"sha256={payload_sha256}.{clean_suffix}",
        )
    )


class LocalObjectStore:
    """Filesystem implementation that preserves S3-compatible keys and URIs."""

    def __init__(self, root: str | Path, *, bucket: str = "shockgraph-local") -> None:
        if not _BUCKET_PATTERN.fullmatch(bucket):
            raise ValueError("bucket must be a valid S3 bucket name")
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.bucket = bucket

    def put_json(self, value: Mapping[str, Any], *, key: str) -> ObjectReference:
        encoded = canonical_json(value) + b"\n"
        checksum = hashlib.sha256(encoded).hexdigest()
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            if path.read_bytes() != encoded:
                raise ObjectIntegrityError(f"immutable object collision: {key}") from None
            return ObjectReference(key, f"s3://{self.bucket}/{key}", checksum, False)

        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return ObjectReference(key, f"s3://{self.bucket}/{key}", checksum, True)

    def _path_for(self, key: str) -> Path:
        pure_key = PurePosixPath(key)
        if pure_key.is_absolute() or ".." in pure_key.parts or not pure_key.parts:
            raise ValueError("object key must be a safe relative POSIX path")
        path = (self.root / Path(*pure_key.parts)).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("object key escapes storage root")
        return path

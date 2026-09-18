from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from shockgraph_data_pipeline.kalshi_contract import payload_sha256

_SOURCE_PATTERN = re.compile(r"^[a-z0-9_-]+$")
_PATH_SEGMENT_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")


class RawPayloadIntegrityError(RuntimeError):
    """Raised when an existing immutable artifact does not match its identity."""


@dataclass(frozen=True, slots=True)
class RawArtifact:
    path: Path
    payload_sha256: str
    created: bool


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError("observed_at must be stored in UTC")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _endpoint_segment(endpoint: str) -> str:
    if not endpoint.startswith("/") or "://" in endpoint:
        raise ValueError("endpoint must be an absolute API path")
    stripped = endpoint.strip("/") or "root"
    return _PATH_SEGMENT_PATTERN.sub("_", stripped).strip("_") or "root"


class ImmutableRawStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        payload: Mapping[str, Any],
        *,
        source: str,
        endpoint: str,
        observed_at: datetime,
        request_params: Mapping[str, Any] | None = None,
    ) -> RawArtifact:
        if not _SOURCE_PATTERN.fullmatch(source):
            raise ValueError("source must contain only lowercase letters, digits, '_' or '-'")

        observed_iso = _utc_iso(observed_at)
        observed_utc = observed_at.astimezone(UTC)
        params = dict(request_params or {})
        payload_hash = payload_sha256(payload)
        request_hash = hashlib.sha256(_canonical_json(params)).hexdigest()[:16]
        timestamp_key = observed_utc.strftime("%H%M%S.%fZ")
        directory = (
            self.root
            / source
            / f"{observed_utc:%Y}"
            / f"{observed_utc:%m}"
            / f"{observed_utc:%d}"
            / _endpoint_segment(endpoint)
            / request_hash
        )
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{timestamp_key}_{payload_hash}.json"
        envelope = {
            "metadata": {
                "schema_version": 1,
                "source": source,
                "endpoint": endpoint,
                "request_params": params,
                "observed_at": observed_iso,
                "payload_sha256": payload_hash,
            },
            "payload": payload,
        }
        encoded = _canonical_json(envelope) + b"\n"

        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            self._verify(path, envelope)
            return RawArtifact(path=path, payload_sha256=payload_hash, created=False)

        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return RawArtifact(path=path, payload_sha256=payload_hash, created=True)

    @staticmethod
    def _verify(path: Path, expected: Mapping[str, Any]) -> None:
        try:
            actual = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RawPayloadIntegrityError(
                f"existing immutable raw artifact is unreadable: {path}"
            ) from error
        if _canonical_json(actual) != _canonical_json(expected):
            raise RawPayloadIntegrityError(
                f"existing immutable raw artifact does not match its identity: {path}"
            )


from __future__ import annotations

import hashlib
from datetime import date

import pytest
from shockgraph_data_pipeline.object_store import (
    LocalObjectStore,
    ObjectIntegrityError,
    build_object_key,
    canonical_json,
)


def test_local_store_preserves_s3_key_and_is_idempotent(tmp_path) -> None:
    payload = {"event": "cpi", "probability": 0.42}
    payload_hash = hashlib.sha256(canonical_json(payload)).hexdigest()
    key = build_object_key(
        namespace="raw",
        source="kalshi",
        observed_date=date(2026, 9, 22),
        payload_sha256=payload_hash,
    )
    store = LocalObjectStore(tmp_path, bucket="shockgraph-local")

    first = store.put_json(payload, key=key)
    second = store.put_json(payload, key=key)

    assert first.created is True
    assert second.created is False
    assert first.uri == f"s3://shockgraph-local/{key}"
    assert key.startswith("raw/kalshi/year=2026/month=09/day=22/")


def test_object_key_cannot_be_overwritten_with_other_content(tmp_path) -> None:
    store = LocalObjectStore(tmp_path)
    key = "raw/kalshi/2026/09/payload.json"
    store.put_json({"value": 1}, key=key)

    with pytest.raises(ObjectIntegrityError, match="collision"):
        store.put_json({"value": 2}, key=key)


def test_object_key_rejects_parent_traversal(tmp_path) -> None:
    store = LocalObjectStore(tmp_path)

    with pytest.raises(ValueError, match="safe relative"):
        store.put_json({"value": 1}, key="../outside.json")

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from shockgraph_data_pipeline.raw_store import ImmutableRawStore, RawPayloadIntegrityError


def test_same_response_is_stored_once_without_overwrite(tmp_path) -> None:
    store = ImmutableRawStore(tmp_path)
    payload = {"events": [{"event_ticker": "KXCPI-26SEP"}], "cursor": ""}
    observed_at = datetime(2026, 9, 17, 12, tzinfo=UTC)

    first = store.save(
        payload,
        source="kalshi",
        endpoint="/events",
        request_params={"limit": 1},
        observed_at=observed_at,
    )
    original_mtime = first.path.stat().st_mtime_ns
    second = store.save(
        payload,
        source="kalshi",
        endpoint="/events",
        request_params={"limit": 1},
        observed_at=observed_at,
    )

    assert first.created is True
    assert second.created is False
    assert first.path == second.path
    assert second.path.stat().st_mtime_ns == original_mtime

    envelope = json.loads(first.path.read_text(encoding="utf-8"))
    assert envelope["metadata"]["payload_sha256"] == first.payload_sha256
    assert envelope["metadata"]["observed_at"] == "2026-09-17T12:00:00Z"
    assert envelope["payload"] == payload


def test_corrupted_existing_artifact_is_not_overwritten(tmp_path) -> None:
    store = ImmutableRawStore(tmp_path)
    payload = {"markets": [{"ticker": "KXCPI-26SEP-T0.3"}]}
    observed_at = datetime(2026, 9, 17, 12, tzinfo=UTC)
    artifact = store.save(
        payload,
        source="kalshi",
        endpoint="/markets",
        observed_at=observed_at,
    )
    artifact.path.write_text("corrupted", encoding="utf-8")

    with pytest.raises(RawPayloadIntegrityError, match="immutable raw artifact"):
        store.save(
            payload,
            source="kalshi",
            endpoint="/markets",
            observed_at=observed_at,
        )


def test_naive_observation_time_is_rejected(tmp_path) -> None:
    store = ImmutableRawStore(tmp_path)

    with pytest.raises(ValueError, match="UTC"):
        store.save(
            {"events": []},
            source="kalshi",
            endpoint="/events",
            observed_at=datetime(2026, 9, 17, 12),
        )


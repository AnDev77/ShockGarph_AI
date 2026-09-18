from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
from shockgraph_collector.client import KalshiPublicClient, RetryPolicy
from shockgraph_data_pipeline.raw_store import ImmutableRawStore


def test_collector_uses_get_without_auth_and_persists_raw_payload(tmp_path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"events": [{"event_ticker": "KXCPI-26SEP"}], "cursor": ""},
        )

    client = KalshiPublicClient(
        transport=httpx.MockTransport(handler),
        clock=lambda: datetime(2026, 9, 17, 12, tzinfo=UTC),
    )
    store = ImmutableRawStore(tmp_path)

    with client:
        artifact = client.collect_json("/events", store, params={"limit": 1})

    assert requests[0].method == "GET"
    assert requests[0].url.params["limit"] == "1"
    assert "kalshi-access-key" not in requests[0].headers
    assert artifact.created is True
    envelope = json.loads(artifact.path.read_text(encoding="utf-8"))
    assert envelope["metadata"]["endpoint"] == "/events"


def test_collector_rejects_private_or_trading_paths() -> None:
    client = KalshiPublicClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))

    with client, pytest.raises(ValueError, match="public read endpoint"):
        client.get_json("/portfolio/orders")


def test_collector_retries_rate_limit_with_bounded_backoff() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, json={"error": "too many requests"})
        return httpx.Response(200, json={"markets": [], "cursor": ""})

    client = KalshiPublicClient(
        transport=httpx.MockTransport(handler),
        retry_policy=RetryPolicy(max_attempts=2, initial_backoff_seconds=0.25),
        sleep=sleeps.append,
    )

    with client:
        payload = client.get_json("/markets")

    assert payload == {"markets": [], "cursor": ""}
    assert attempts == 2
    assert sleeps == [0.25]


def test_collector_paginates_and_stores_each_raw_page(tmp_path) -> None:
    cursors_seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        cursors_seen.append(cursor)
        if cursor is None:
            return httpx.Response(
                200,
                json={"events": [{"event_ticker": "EVENT-1"}], "cursor": "page-2"},
            )
        return httpx.Response(
            200,
            json={"events": [{"event_ticker": "EVENT-2"}], "cursor": ""},
        )

    client = KalshiPublicClient(
        transport=httpx.MockTransport(handler),
        clock=lambda: datetime(2026, 9, 17, 12, tzinfo=UTC),
    )
    store = ImmutableRawStore(tmp_path)

    with client:
        artifacts = client.collect_pages(
            "/events",
            store,
            collection_key="events",
            params={"limit": 1},
        )

    assert cursors_seen == [None, "page-2"]
    assert len(artifacts) == 2
    assert all(artifact.created for artifact in artifacts)

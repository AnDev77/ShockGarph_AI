from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from shockgraph_collector.alpaca import AlpacaMarketDataClient
from shockgraph_data_pipeline.raw_store import ImmutableRawStore


def test_alpaca_collector_uses_read_only_bars_and_keeps_credentials_out_of_raw_store(
    tmp_path,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "bars": {
                    "SPY": [
                        {
                            "t": "2026-03-11T12:28:00Z",
                            "o": 100.0,
                            "h": 100.2,
                            "l": 99.9,
                            "c": 100.1,
                            "v": 12,
                        }
                    ]
                },
                "next_page_token": None,
            },
        )

    with AlpacaMarketDataClient(
        api_key_id="key-id",
        api_secret_key="secret-key",
        transport=httpx.MockTransport(handler),
        clock=lambda: datetime(2026, 9, 27, 1, tzinfo=UTC),
    ) as client:
        pages = client.collect_stock_bars(
            ImmutableRawStore(tmp_path),
            symbols=("SPY",),
            start=datetime(2026, 3, 11, 12, 28, tzinfo=UTC),
            end=datetime(2026, 3, 11, 12, 29, tzinfo=UTC),
            feed="iex",
        )

    assert len(pages) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/v2/stocks/bars"
    assert requests[0].headers["APCA-API-KEY-ID"] == "key-id"
    assert requests[0].headers["APCA-API-SECRET-KEY"] == "secret-key"
    assert requests[0].url.params["symbols"] == "SPY"
    assert requests[0].url.params["timeframe"] == "1Min"
    envelope = json.loads(pages[0].artifact.path.read_text(encoding="utf-8"))
    serialized = json.dumps(envelope)
    assert "key-id" not in serialized
    assert "secret-key" not in serialized
    assert envelope["metadata"]["request_params"]["feed"] == "iex"


def test_alpaca_collector_paginates_with_bounded_page_tokens(tmp_path) -> None:
    tokens: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.params.get("page_token")
        tokens.append(token)
        next_token = "second" if token is None else None
        return httpx.Response(200, json={"bars": {}, "next_page_token": next_token})

    with AlpacaMarketDataClient(
        api_key_id="key-id",
        api_secret_key="secret-key",
        transport=httpx.MockTransport(handler),
    ) as client:
        pages = client.collect_stock_bars(
            ImmutableRawStore(tmp_path),
            symbols=("SPY", "TLT", "GLD"),
            start=datetime(2026, 3, 11, 12, 28, tzinfo=UTC),
            end=datetime(2026, 3, 11, 13, 1, tzinfo=UTC),
            feed="iex",
        )

    assert tokens == [None, "second"]
    assert len(pages) == 2


def test_historical_sip_is_default_and_recent_sip_is_rejected_before_request(tmp_path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"bars": {}, "next_page_token": None})

    now = datetime(2026, 9, 27, 12, tzinfo=UTC)
    with AlpacaMarketDataClient(
        api_key_id="key-id",
        api_secret_key="secret-key",
        transport=httpx.MockTransport(handler),
        clock=lambda: now,
    ) as client:
        client.collect_stock_bars(
            ImmutableRawStore(tmp_path),
            symbols=("SPY",),
            start=now - timedelta(days=1, minutes=2),
            end=now - timedelta(days=1),
        )
        assert requests[0].url.params["feed"] == "sip"
        with pytest.raises(ValueError, match="15 minutes"):
            client.collect_stock_bars(
                ImmutableRawStore(tmp_path),
                symbols=("SPY",),
                start=now - timedelta(minutes=20),
                end=now - timedelta(minutes=14),
            )
    assert len(requests) == 1


def test_alpaca_collector_rejects_a_repeated_page_token(tmp_path) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"bars": {}, "next_page_token": "same"})

    with (
        AlpacaMarketDataClient(
            api_key_id="key-id",
            api_secret_key="secret-key",
            transport=httpx.MockTransport(handler),
        ) as client,
        pytest.raises(ValueError, match="repeated"),
    ):
        client.collect_stock_bars(
            ImmutableRawStore(tmp_path),
            symbols=("SPY",),
            start=datetime(2026, 3, 11, 12, 28, tzinfo=UTC),
            end=datetime(2026, 3, 11, 12, 29, tzinfo=UTC),
            feed="iex",
        )


def test_alpaca_collector_rejects_unknown_assets_and_invalid_time_range(tmp_path) -> None:
    with AlpacaMarketDataClient(
        api_key_id="key-id",
        api_secret_key="secret-key",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})),
    ) as client:
        with pytest.raises(ValueError, match="SPY, TLT, or GLD"):
            client.collect_stock_bars(
                ImmutableRawStore(tmp_path),
                symbols=("QQQ",),
                start=datetime(2026, 3, 11, 12, 28, tzinfo=UTC),
                end=datetime(2026, 3, 11, 12, 29, tzinfo=UTC),
            )
        with pytest.raises(ValueError, match="start must be before end"):
            client.collect_stock_bars(
                ImmutableRawStore(tmp_path),
                symbols=("SPY",),
                start=datetime(2026, 3, 11, 12, 29, tzinfo=UTC),
                end=datetime(2026, 3, 11, 12, 29, tzinfo=UTC),
            )

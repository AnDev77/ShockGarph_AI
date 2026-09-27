from __future__ import annotations

import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from shockgraph_collector.alpaca import AlpacaMarketDataClient
from shockgraph_data_pipeline.raw_store import ImmutableRawStore

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from collect_alpaca_etf_bars import (  # noqa: E402
    collect_alpaca_asset_dataset,
    credentials_from_env,
)


def _write_release(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "event_id",
                "event_ticker",
                "reference_month",
                "release_at",
                "actual_mom_first",
                "threshold",
                "bls_outcome",
                "source_url",
                "raw_hash",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "event_id": "cpi-2026-02",
                "event_ticker": "KXCPI-26FEB",
                "reference_month": "2026-02-01",
                "release_at": "2026-03-11T12:30:00+00:00",
                "actual_mom_first": 0.3,
                "threshold": 0.3,
                "bls_outcome": "no",
                "source_url": "https://www.bls.gov/news.release/archives/cpi_03112026.htm",
                "raw_hash": "a" * 64,
            }
        )


def _bar(symbol: str, source_start: str, price: float) -> dict[str, object]:
    return {
        "t": source_start,
        "o": price,
        "h": price,
        "l": price,
        "c": price,
        "v": 10,
        "symbol": symbol,
    }


def test_alpaca_asset_dataset_builds_complete_three_asset_event_windows(tmp_path) -> None:
    release_path = tmp_path / "release_vintage.csv"
    _write_release(release_path)
    requested: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request)
        bars = {
            symbol: [
                _bar(symbol, "2026-03-11T12:28:00Z", base),
                _bar(symbol, "2026-03-11T12:34:00Z", base + 1),
                _bar(symbol, "2026-03-11T12:59:00Z", base + 2),
            ]
            for symbol, base in (("SPY", 100), ("TLT", 90), ("GLD", 200))
        }
        return httpx.Response(200, json={"bars": bars, "next_page_token": None})

    with AlpacaMarketDataClient(
        api_key_id="key-id",
        api_secret_key="secret-key",
        transport=httpx.MockTransport(handler),
        clock=lambda: datetime(2026, 9, 27, 2, tzinfo=UTC),
    ) as client:
        destination = collect_alpaca_asset_dataset(
            client,
            ImmutableRawStore(tmp_path / "raw"),
            release_path,
            tmp_path / "output",
            feed="iex",
        )

    assert len(requested) == 1
    assert requested[0].url.params["start"] == "2026-03-11T12:28:00Z"
    assert requested[0].url.params["end"] == "2026-03-11T13:00:00Z"
    metadata = json.loads(destination.joinpath("metadata.json").read_text(encoding="utf-8"))
    assert metadata["feed"] == "iex"
    assert metadata["release_events"] == 1
    assert metadata["bar_rows"] == 9
    assert metadata["common_events"] == 1
    assert metadata["common_event_ids"] == ["cpi-2026-02"]
    with destination.joinpath("asset_minute_bars.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["asset_id"] for row in rows} == {"SPY", "TLT", "GLD"}
    assert {row["price_at"] for row in rows} == {
        "2026-03-11T12:29:00Z",
        "2026-03-11T12:35:00Z",
        "2026-03-11T13:00:00Z",
    }
    assert all(row["extended_hours"] == "true" for row in rows)


def test_alpaca_credentials_are_required_without_guessing_or_demo_fallback() -> None:
    with pytest.raises(RuntimeError, match="ALPACA_API_KEY_ID"):
        credentials_from_env({})
    assert credentials_from_env(
        {"ALPACA_API_KEY_ID": "key-id", "ALPACA_API_SECRET_KEY": "secret-key"}
    ) == ("key-id", "secret-key")

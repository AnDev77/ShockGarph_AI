from __future__ import annotations

import base64
import json
from datetime import UTC, date, datetime

import httpx
import pytest
from shockgraph_collector.alpaca_bars import AlpacaDailyCollector
from shockgraph_data_pipeline.daily_price_import import import_daily_prices
from shockgraph_data_pipeline.raw_store import ImmutableRawStore
from shockgraph_risk.daily import PriceSnapshot, _snapshot_as_of

from scripts.collect_alpaca_prices import main

CAPTURED = datetime(2026, 4, 9, 22, tzinfo=UTC)
START, END = date(2026, 4, 6), date(2026, 4, 8)


def _bar(day: int, close: float) -> dict[str, object]:
    return {"t": f"2026-04-{day:02d}T04:00:00Z", "c": close, "v": 1000}


def test_alpaca_sip_pages_preserve_originals_and_connect_price_snapshot(tmp_path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "data.alpaca.markets"
        assert request.url.params["feed"] == "sip"
        assert request.url.params["timeframe"] == "1Day"
        assert request.url.params["start"] == "2026-04-06"
        assert request.url.params["end"] == "2026-04-08T23:59:59Z"
        assert request.url.params["adjustment"] in ("raw", "all")
        adjustment = request.url.params["adjustment"]
        cursor = request.url.params.get("page_token")
        days = [6, 7] if cursor is None else [8]
        bars = [_bar(day, 100 + day - (1 if adjustment == "all" else 0))
                for day in days]
        return httpx.Response(200, json={"bars": bars,
                                         "next_page_token": "next" if cursor is None else None})

    with AlpacaDailyCollector("example-id", "example-secret",
                              transport=httpx.MockTransport(handler),
                              clock=lambda: CAPTURED) as collector:
        capture = collector.collect("TLT", START, END, ImmutableRawStore(tmp_path))
    assert len(requests) == 4
    assert all(request.headers["APCA-API-KEY-ID"] == "example-id" for request in requests)
    assert all(request.headers["APCA-API-SECRET-KEY"] == "example-secret"
               for request in requests)
    assert len(capture.raw_artifacts) == 4
    assert capture.session_count == 3
    archived = capture.raw_artifacts[0].path.read_text(encoding="utf-8")
    assert "example-secret" not in archived
    payload = json.loads(archived)["payload"]
    assert json.loads(base64.b64decode(payload["body_base64"]))["bars"][0]["c"] == 106

    imported = import_daily_prices(
        capture.csv_bytes, store=ImmutableRawStore(tmp_path), source="alpaca-sip",
        captured_at=capture.captured_at, start=START, end=END, symbol="TLT",
        venue="US_SIP", full_snapshot=True,
    )
    assert imported.quality.structurally_ready
    assert imported.quality.venue == "US_SIP"
    assert imported.prices[0].close == 106
    assert imported.prices[0].adjusted_close == 105
    assert all(row.available_at == CAPTURED for row in imported.prices)
    with pytest.raises(ValueError, match="no complete price snapshot"):
        _snapshot_as_of((PriceSnapshot(CAPTURED, imported.prices),),
                        datetime(2026, 4, 8, 22, tzinfo=UTC))


def test_alpaca_rejects_missing_adjusted_day_and_repeated_page_token(tmp_path) -> None:
    def missing(request: httpx.Request) -> httpx.Response:
        days = [6, 7, 8] if request.url.params["adjustment"] == "raw" else [6, 7]
        return httpx.Response(200, json={"bars": [_bar(day, 100) for day in days],
                                         "next_page_token": None})

    with AlpacaDailyCollector("id", "secret", transport=httpx.MockTransport(missing),
                              clock=lambda: CAPTURED) as collector, pytest.raises(
                                  ValueError, match="cover all reviewed sessions"
                              ):
        collector.collect("SPY", START, END, ImmutableRawStore(tmp_path))

    def repeated(request: httpx.Request) -> httpx.Response:
        day = 6 if "page_token" not in request.url.params else 7
        return httpx.Response(200, json={"bars": [_bar(day, 100)],
                                         "next_page_token": "same"})

    with AlpacaDailyCollector("id", "secret", transport=httpx.MockTransport(repeated),
                              clock=lambda: CAPTURED) as collector, pytest.raises(
                                  ValueError, match="pagination did not advance"
                              ):
        collector.collect("TLT", START, END, ImmutableRawStore(tmp_path))


def test_alpaca_cli_reports_missing_credentials_without_disclosing_secret(
    monkeypatch, capsys,
) -> None:
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    assert main(["--end", "2026-04-08"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "missing_credentials"
    assert report["required_environment"] == ["APCA_API_KEY_ID", "APCA_API_SECRET_KEY"]


def test_alpaca_cli_writes_two_private_snapshots_and_source_manifest(
    tmp_path, monkeypatch, capsys,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        symbol = request.url.path.split("/")[3]
        adjusted = request.url.params["adjustment"] == "all"
        base = 80 if symbol == "TLT" else 400
        return httpx.Response(200, json={
            "bars": [_bar(day, base + day - int(adjusted)) for day in (6, 7, 8)],
            "next_page_token": None,
        })

    monkeypatch.setenv("APCA_API_KEY_ID", "test-id")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "test-secret")
    monkeypatch.setattr(
        "scripts.collect_alpaca_prices.AlpacaDailyCollector",
        lambda key_id, secret: AlpacaDailyCollector(
            key_id, secret, transport=httpx.MockTransport(handler), clock=lambda: CAPTURED
        ),
    )
    output = tmp_path / "private"
    assert main(["--start", START.isoformat(), "--end", END.isoformat(),
                 "--raw-root", str(tmp_path / "raw"), "--output-dir", str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert [row["symbol"] for row in result["prices"]] == ["TLT", "SPY"]
    assert result["actual_response_capture_times_recorded"] is True
    assert result["historical_provider_release_times_verified"] is False
    assert result["redistribution_rights_verified"] is False
    assert "test-secret" not in json.dumps(result)
    assert (output / "TLT" / "20260409T220000.000000Z.csv").is_file()
    assert (output / "SPY" / "20260409T220000.000000Z.csv").is_file()
    assert json.loads((output / "captures" / "2026-04-09T22-00-00+00-00.json")
                      .read_text(encoding="utf-8"))["prices"] == result["prices"]

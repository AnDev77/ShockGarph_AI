from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, date, datetime

import httpx
import pytest
from shockgraph_collector.treasury_rates import TreasuryYieldCollector, load_treasury_history
from shockgraph_data_pipeline.raw_store import ImmutableRawStore

from scripts.report_treasury_coverage import report_coverage

SAMPLE = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
      xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices">
  <entry><content type="application/xml"><m:properties>
    <d:NEW_DATE>2026-10-19T00:00:00</d:NEW_DATE>
    <d:BC_10YEAR>4.00</d:BC_10YEAR>
  </m:properties></content></entry>
  <entry><content type="application/xml"><m:properties>
    <d:NEW_DATE>2026-10-20T00:00:00</d:NEW_DATE>
    <d:BC_10YEAR>4.05</d:BC_10YEAR>
  </m:properties></content></entry>
</feed>"""


def test_keyless_treasury_collection_preserves_raw_and_actual_capture_time(tmp_path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=SAMPLE,
                              headers={"content-type": "application/xml"})

    captured = datetime(2026, 10, 22, 1, 5, tzinfo=UTC)
    store = ImmutableRawStore(tmp_path)
    with TreasuryYieldCollector(transport=httpx.MockTransport(handler),
                                clock=lambda: captured) as client:
        first = client.collect_month(2026, 10, store)
        repeated = client.collect_month(2026, 10, store)

    assert requests[0].method == "GET"
    assert requests[0].url.host == "home.treasury.gov"
    assert requests[0].url.params["data"] == "daily_treasury_yield_curve"
    assert requests[0].url.params["field_tdr_date_value_month"] == "202610"
    assert "authorization" not in requests[0].headers
    assert first.captured_at == captured
    assert [row.observation_date for row in first.observations] == [
        date(2026, 10, 19), date(2026, 10, 20)
    ]
    assert [row.value_percent for row in first.observations] == [4.00, 4.05]
    assert all(row.captured_at == captured for row in first.observations)
    assert first.raw_file_sha256 == hashlib.sha256(SAMPLE).hexdigest()
    assert first.raw_artifact.created is True
    assert repeated.raw_artifact.created is False
    envelope = json.loads(first.raw_artifact.path.read_text(encoding="utf-8"))
    assert base64.b64decode(envelope["payload"]["body_base64"]) == SAMPLE
    assert envelope["metadata"]["observed_at"] == "2026-10-22T01:05:00Z"


def test_treasury_rejects_wrong_month_duplicates_and_future_observations(tmp_path) -> None:
    for invalid in (
        SAMPLE.replace(b"2026-10-20", b"2026-09-20"),
        SAMPLE.replace(b"2026-10-20", b"2026-10-19"),
        SAMPLE.replace(b"2026-10-20", b"2026-10-23"),
    ):
        with TreasuryYieldCollector(
            transport=httpx.MockTransport(lambda _, body=invalid: httpx.Response(
                200, content=body, headers={"content-type": "text/xml"}
            )),
            clock=lambda: datetime(2026, 10, 22, 1, 5, tzinfo=UTC),
        ) as client, pytest.raises(ValueError):
            client.collect_month(2026, 10, ImmutableRawStore(tmp_path))
    assert not list((tmp_path / "us-treasury").rglob("*.json"))


def test_treasury_rejects_html_and_non_finite_rate(tmp_path) -> None:
    for payload, content_type in (
        (b"<html>blocked</html>", "text/html"),
        (SAMPLE.replace(b"4.05", b"NaN"), "application/xml"),
    ):
        def handler(_: httpx.Request, body: bytes = payload,
                    media: str = content_type) -> httpx.Response:
            return httpx.Response(200, content=body, headers={"content-type": media})

        with TreasuryYieldCollector(
            transport=httpx.MockTransport(handler),
            clock=lambda: datetime(2026, 10, 22, 1, 5, tzinfo=UTC),
        ) as client, pytest.raises(ValueError):
            client.collect_month(2026, 10, ImmutableRawStore(tmp_path))


def test_archived_treasury_versions_keep_real_capture_order_and_detect_tampering(tmp_path) -> None:
    store = ImmutableRawStore(tmp_path)
    captured = datetime(2026, 10, 22, 1, 5, tzinfo=UTC)
    with TreasuryYieldCollector(
        transport=httpx.MockTransport(lambda _: httpx.Response(
            200, content=SAMPLE, headers={"content-type": "application/xml"}
        )), clock=lambda: captured,
    ) as client:
        first = client.collect_month(2026, 10, store)
    with TreasuryYieldCollector(
        transport=httpx.MockTransport(lambda _: httpx.Response(
            200, content=SAMPLE.replace(b"4.05", b"4.15"),
            headers={"content-type": "application/xml"}
        )), clock=lambda: datetime(2026, 10, 23, 1, 5, tzinfo=UTC),
    ) as client:
        client.collect_month(2026, 10, store)
    history = load_treasury_history(tmp_path)
    assert [(row.observation_date, row.value_percent, row.captured_at)
            for row in history if row.observation_date == date(2026, 10, 20)] == [
        (date(2026, 10, 20), 4.05, captured),
        (date(2026, 10, 20), 4.15, datetime(2026, 10, 23, 1, 5, tzinfo=UTC)),
    ]
    tampered = json.loads(first.raw_artifact.path.read_text(encoding="utf-8"))
    tampered["payload"]["body_base64"] = base64.b64encode(b"<broken/>").decode("ascii")
    first.raw_artifact.path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_treasury_history(tmp_path)


def test_coverage_distinguishes_shared_dates_from_later_capturable_sessions(tmp_path) -> None:
    with TreasuryYieldCollector(
        transport=httpx.MockTransport(lambda _: httpx.Response(
            200, content=SAMPLE, headers={"content-type": "application/xml"}
        )), clock=lambda: datetime(2026, 10, 22, 1, 5, tzinfo=UTC),
    ) as client:
        client.collect_month(2026, 10, ImmutableRawStore(tmp_path))
    price_path = tmp_path / "private-prices.csv"
    price_path.write_text("session_date,adjusted_close\n2026-10-19,100\n"
                          "2026-10-20,101\n2026-10-21,102\n2026-10-22,103\n",
                          encoding="utf-8")
    result = report_coverage(price_path, tmp_path)
    assert result["price_session_count"] == 4
    assert result["same_date_observation_overlap"] == 2
    assert result["price_sessions_strictly_after_first_capture"] == 1
    assert result["sessions_with_earlier_treasury_capture"] == 1
    assert result["public_performance_allowed"] is False

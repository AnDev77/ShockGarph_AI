"""Private QQQ raw-only archive is independent of prospective TLT/SPY scores."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from shockgraph_collector.alpaca_bars import AlpacaDailyCollector

from scripts.archive_private_research_capture import (
    archive_qqq_capture,
    audit_qqq_capture,
)
from scripts.archive_private_research_capture import (
    main as archive_main,
)
from scripts.collect_alpaca_prices import main as collect_main


class AlreadyExists(Exception):
    response = {"Error": {"Code": "PreconditionFailed"}}


class MemoryS3:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, dict[str, str]]] = {}
        self.written_at = datetime(2026, 4, 9, 23, tzinfo=UTC)

    def put_object(self, *, Bucket: str, Key: str, Body: bytes,
                   Metadata: dict[str, str], IfNoneMatch: str) -> None:
        assert Bucket == "private-risk-research" and IfNoneMatch == "*"
        if Key in self.objects:
            raise AlreadyExists
        self.objects[Key] = Body, Metadata

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        body, metadata = self.objects[Key]
        return {"ContentLength": len(body), "Metadata": metadata,
                "LastModified": self.written_at}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        return {"Body": io.BytesIO(self.objects[Key][0])}


def _replace_hashed_source(client: MemoryS3, index_key: str, source_key: str,
                           changed: bytes) -> None:
    """Simulate a self-consistent object/index rewrite, beyond a simple bit flip."""
    _, metadata = client.objects[source_key]
    digest = hashlib.sha256(changed).hexdigest()
    client.objects[source_key] = changed, {**metadata, "sha256": digest}
    index = json.loads(client.objects[index_key][0])
    for source in index["source_objects"]:
        if source["key"] == source_key:
            source["sha256"] = digest
    encoded = json.dumps(index, sort_keys=True, separators=(",", ":")).encode()
    _, index_metadata = client.objects[index_key]
    client.objects[index_key] = encoded, {
        **index_metadata, "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _manifest(tmp_path: Path, monkeypatch, capsys, symbol: str = "QQQ") -> tuple[Path, Path]:
    capture = datetime(2026, 4, 9, 22, tzinfo=UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/v2/stocks/{symbol}/bars"
        adjusted = int(request.url.params["adjustment"] == "all")
        return httpx.Response(200, json={
            "bars": [{"t": f"2026-04-{day:02d}T04:00:00Z",
                      "c": 200 + day - adjusted, "v": 1000} for day in (6, 7, 8)],
            "next_page_token": None,
        })

    monkeypatch.setenv("APCA_API_KEY_ID", "test-id")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "test-secret")
    monkeypatch.setattr(
        "scripts.collect_alpaca_prices.AlpacaDailyCollector",
        lambda key_id, secret: AlpacaDailyCollector(
            key_id, secret, transport=httpx.MockTransport(handler), clock=lambda: capture
        ),
    )
    output, raw_root = tmp_path / "private", tmp_path / "raw"
    assert collect_main(["--start", date(2026, 4, 6).isoformat(),
                         "--end", date(2026, 4, 8).isoformat(),
                         "--symbols", symbol, "--raw-root", str(raw_root),
                         "--output-dir", str(output)]) == 0
    capsys.readouterr()
    return next((output / "captures").glob("*.json")), raw_root


def test_qqq_archive_rechecks_all_private_bytes_and_is_write_once(
    tmp_path, monkeypatch, capsys,
) -> None:
    manifest, raw_root = _manifest(tmp_path, monkeypatch, capsys)
    client = MemoryS3()
    first = archive_qqq_capture(manifest, raw_root=raw_root, s3=client,
                                bucket="private-risk-research", prefix="research")
    assert first["status"] == "research_price_only"
    assert first["created_object_count"] == first["source_object_count"] + 1
    assert "/qqq-captures/" in first["index_key"]
    assert not any("/captures/" in key for key in client.objects)
    index = json.loads(client.objects[first["index_key"]][0])
    assert index["forecasts"] == []
    assert index["redistribution_rights_verified"] is False
    checked = audit_qqq_capture(client, bucket="private-risk-research",
                                index_key=first["index_key"])
    assert checked["status"] == "research_price_readback_verified"
    second = archive_qqq_capture(manifest, raw_root=raw_root, s3=client,
                                 bucket="private-risk-research", prefix="research")
    assert second["created_object_count"] == 0
    source = index["source_objects"][0]["key"]
    data, metadata = client.objects[source]
    client.objects[source] = data + b"tampered", metadata
    with pytest.raises(ValueError, match="readback hash"):
        audit_qqq_capture(client, bucket="private-risk-research",
                          index_key=first["index_key"])


def test_qqq_archive_rejects_other_symbol_and_budget_before_writing(
    tmp_path, monkeypatch, capsys,
) -> None:
    manifest, raw_root = _manifest(tmp_path, monkeypatch, capsys, symbol="SPY")
    client = MemoryS3()
    with pytest.raises(ValueError, match="QQQ"):
        archive_qqq_capture(manifest, raw_root=raw_root, s3=client,
                            bucket="private-risk-research", prefix="research")
    assert not client.objects
    qqq_manifest, qqq_root = _manifest(tmp_path / "qqq", monkeypatch, capsys)
    with pytest.raises(ValueError, match="budget"):
        archive_qqq_capture(qqq_manifest, raw_root=qqq_root, s3=client,
                            bucket="private-risk-research", prefix="research",
                            budget_check=lambda _: (_ for _ in ()).throw(ValueError("budget")))
    assert not client.objects


def test_qqq_archive_cli_reports_audit_without_source_or_object_names(
    tmp_path, monkeypatch, capsys,
) -> None:
    manifest, raw_root = _manifest(tmp_path, monkeypatch, capsys)
    client = MemoryS3()
    monkeypatch.setattr("scripts.archive_private_research_capture.configured_r2",
                        lambda: (client, "private-risk-research"))
    monkeypatch.setattr("scripts.archive_private_research_capture.bucket_budget_guard",
                        lambda _client, _bucket: lambda _bytes: None)
    assert archive_main(["--manifest", str(manifest), "--raw-root", str(raw_root),
                         "--prefix", "research"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "research_price_readback_verified"
    assert report["forecast_count"] == 0
    assert "index_key" not in report and "prices" not in report
    assert "test-secret" not in json.dumps(report)


@pytest.mark.parametrize("change", ["reorder", "late_availability", "wrong_close_time",
                                    "missing_session"])
def test_qqq_readback_rejects_coherently_rehashed_bad_time_series(
    tmp_path, monkeypatch, capsys, change: str,
) -> None:
    manifest, raw_root = _manifest(tmp_path, monkeypatch, capsys)
    client = MemoryS3()
    report = archive_qqq_capture(manifest, raw_root=raw_root, s3=client,
                                 bucket="private-risk-research", prefix="research")
    index_key = report["index_key"]
    csv_key = index_key.removesuffix("records/index.json") + "QQQ/prices.csv"
    lines = client.objects[csv_key][0].decode().splitlines()
    if change == "reorder":
        lines[1], lines[2] = lines[2], lines[1]
    elif change == "missing_session":
        del lines[2]
    else:
        cells = lines[1].split(",")
        if change == "late_availability":
            cells[2] = "2026-04-10T00:00:00+00:00"
        else:
            cells[1] = "2026-04-06T00:00:00+00:00"
        lines[1] = ",".join(cells)
    _replace_hashed_source(client, index_key, csv_key, ("\n".join(lines) + "\n").encode())
    with pytest.raises(ValueError, match="QQQ research (snapshot|time)"):
        audit_qqq_capture(client, bucket="private-risk-research", index_key=index_key)

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from shockgraph_data_pipeline.market_calendar import nasdaq_sessions
from shockgraph_data_pipeline.raw_store import ImmutableRawStore

from scripts.archive_forward_capture import archive_capture, main


class AlreadyExists(Exception):
    response = {"Error": {"Code": "PreconditionFailed"}}


class MemoryS3:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes,
                   Metadata: dict[str, str], ServerSideEncryption: str,
                   IfNoneMatch: str) -> None:
        assert Bucket == "private-risk-research"
        assert ServerSideEncryption == "AES256"
        assert IfNoneMatch == "*"
        if Key in self.objects:
            raise AlreadyExists
        self.objects[Key] = Body, Metadata["sha256"]

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        body, digest = self.objects[Key]
        return {"ContentLength": len(body), "Metadata": {"sha256": digest}}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        return {"Body": io.BytesIO(self.objects[Key][0])}


def _manifest(tmp_path: Path, *, full_history: bool = False) -> tuple[Path, Path]:
    root = tmp_path / "raw"
    store = ImmutableRawStore(root)
    private = tmp_path / "private"
    sessions = (nasdaq_sessions(date(2026, 1, 2), date(2026, 9, 30))[:125]
                if full_history else nasdaq_sessions(date(2026, 4, 6), date(2026, 4, 8)))
    capture_time = (sessions[-1].close_at + timedelta(minutes=40) if full_history else
                    datetime(2026, 4, 9, 22, tzinfo=UTC))
    entries = []
    for symbol in ("TLT", "SPY"):
        path = private / symbol / "capture.csv"
        path.parent.mkdir(parents=True)
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, lineterminator="\n")
            writer.writerow(("session_date", "observed_at", "available_at", "close",
                             "adjusted_close", "volume"))
            for offset, session in enumerate(sessions):
                writer.writerow((session.session_date, session.close_at.isoformat(),
                                 capture_time.isoformat(), 100 + offset, 99 + offset, 1000))
        data = path.read_bytes()
        response = f"{symbol} raw source".encode()
        raw = store.save({"format": "application/json",
                          "body_base64": base64.b64encode(response).decode(),
                          "file_sha256": hashlib.sha256(response).hexdigest()},
                         source="alpaca", endpoint=f"/v2/stocks/{symbol}/bars",
                         observed_at=capture_time)
        normalized = store.save({"format": "text/csv; charset=utf-8",
                                 "content_base64": base64.b64encode(data).decode(),
                                 "file_sha256": hashlib.sha256(data).hexdigest()},
                                source="alpaca-sip", endpoint="/local/daily-adjusted-csv",
                                observed_at=capture_time, request_params={"symbol": symbol})
        entries.append({"symbol": symbol, "feed": "sip", "capture": capture_time.isoformat(),
                        "snapshot_path": str(path), "session_count": len(sessions),
                        "normalized_csv_sha256": hashlib.sha256(data).hexdigest(),
                        "source_raw_artifact_paths": [str(raw.path)],
                        "source_raw_payload_hashes": [raw.payload_sha256],
                        "source_response_sha256": [hashlib.sha256(response).hexdigest()],
                        "normalized_raw_artifact_path": str(normalized.path),
                        "normalized_raw_payload_hash": normalized.payload_sha256})
    manifest = private / "captures" / "capture.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"status": "archived_research_only", "prices": entries,
                                    "redistribution_rights_verified": False}), encoding="utf-8")
    return manifest, root


def test_private_archive_is_immutable_and_does_not_backdate_late_forecast(tmp_path) -> None:
    manifest, raw_root = _manifest(tmp_path)
    client = MemoryS3()
    recorded_at = datetime(2026, 4, 9, 22, 20, tzinfo=UTC)
    first = archive_capture(manifest, raw_root=raw_root, s3=client,
                            bucket="private-risk-research", prefix="research",
                            prediction_at=recorded_at,
                            receipt_clock=lambda: recorded_at)
    assert first["status"] == "snapshot_only_preopen_gate_failed"
    assert first["forecast_count"] == 0
    assert first["created_object_count"] == 8
    second = archive_capture(manifest, raw_root=raw_root, s3=client,
                             bucket="private-risk-research", prefix="research",
                             prediction_at=recorded_at,
                             receipt_clock=lambda: recorded_at)
    assert second["created_object_count"] == 0
    assert len(client.objects) == 8
    index_key = first["index_key"]
    assert json.loads(client.objects[index_key][0])["public_performance_allowed"] is False
    data, _ = client.objects[index_key]
    client.objects[index_key] = data, "0" * 64
    with pytest.raises(ValueError, match="immutable object collision"):
        archive_capture(manifest, raw_root=raw_root, s3=client,
                        bucket="private-risk-research", prefix="research",
                        prediction_at=recorded_at,
                        receipt_clock=lambda: recorded_at)
    client.objects[index_key] = data[:-2] + b"x\n", hashlib.sha256(data).hexdigest()
    with pytest.raises(ValueError, match="immutable object collision"):
        archive_capture(manifest, raw_root=raw_root, s3=client,
                        bucket="private-risk-research", prefix="research",
                        prediction_at=recorded_at,
                        receipt_clock=lambda: recorded_at)


def test_private_archive_rejects_changed_raw_or_outside_path(tmp_path) -> None:
    manifest, raw_root = _manifest(tmp_path)
    client = MemoryS3()
    entry = json.loads(manifest.read_text())
    raw = Path(entry["prices"][0]["source_raw_artifact_paths"][0])
    raw.write_bytes(raw.read_bytes() + b" ")
    with pytest.raises(ValueError, match="raw artifact"):
        archive_capture(manifest, raw_root=raw_root, s3=client,
                        bucket="private-risk-research", prefix="research",
                        prediction_at=datetime(2026, 4, 9, 22, 20, tzinfo=UTC),
                        receipt_clock=lambda: datetime(2026, 4, 9, 22, 20, tzinfo=UTC))
    assert not client.objects
    manifest, raw_root = _manifest(tmp_path / "again")
    entry = json.loads(manifest.read_text())
    entry["prices"][0]["source_raw_artifact_paths"] = [str(tmp_path / "escape.json")]
    manifest.write_text(json.dumps(entry), encoding="utf-8")
    with pytest.raises(ValueError, match="outside private raw root"):
        archive_capture(manifest, raw_root=raw_root, s3=client,
                        bucket="private-risk-research", prefix="research",
                        prediction_at=datetime(2026, 4, 9, 22, 20, tzinfo=UTC),
                        receipt_clock=lambda: datetime(2026, 4, 9, 22, 20, tzinfo=UTC))


def test_private_archive_records_forecasts_only_before_next_open(tmp_path) -> None:
    manifest, raw_root = _manifest(tmp_path, full_history=True)
    client = MemoryS3()
    capture = datetime.fromisoformat(json.loads(manifest.read_text())["prices"][0]["capture"])
    recorded_at = capture + timedelta(minutes=5)
    first = archive_capture(manifest, raw_root=raw_root, s3=client,
                            bucket="private-risk-research", prefix="research",
                            prediction_at=recorded_at,
                            receipt_clock=lambda: recorded_at)
    assert first["status"] == "forward_forecasts_archived"
    index = json.loads(client.objects[first["index_key"]][0])
    assert len(index["forecasts"]) == 2
    assert all(len(item["horizons"]) == 2 for item in index["forecasts"])
    next_close = nasdaq_sessions(
        date.fromisoformat(index["forecasts"][0]["origin_session"]) + timedelta(days=1),
        date(2026, 12, 31),
    )[0].close_at
    next_open = datetime.combine(next_close.astimezone(ZoneInfo("America/New_York")).date(),
                                 time(9, 30), ZoneInfo("America/New_York")).astimezone(UTC)
    late = archive_capture(manifest, raw_root=raw_root, s3=client,
                           bucket="private-risk-research", prefix="research",
                           prediction_at=recorded_at,
                           receipt_clock=lambda: next_open - timedelta(minutes=30))
    assert late["status"] == "snapshot_only_preopen_gate_failed"
    assert late["forecast_count"] == 0
    assert late["created_object_count"] == 1


def test_cli_requires_private_bucket_before_loading_the_archive(monkeypatch, capsys) -> None:
    monkeypatch.delenv("SHOCKGRAPH_PRIVATE_BUCKET", raising=False)
    assert main(["--manifest", "/missing/manifest.json"]) == 2
    assert json.loads(capsys.readouterr().out) == {"status": "private_archive_not_configured"}

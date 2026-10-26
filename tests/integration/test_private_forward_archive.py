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

from scripts import private_r2
from scripts.archive_forward_capture import archive_capture, audit_capture, main
from scripts.audit_private_capture import latest_capture
from scripts.audit_private_capture import main as audit_main
from scripts.check_capture_due import capture_due
from scripts.private_r2 import MAX_BUCKET_BYTES, MAX_CAPTURE_BYTES, bucket_budget_guard


class AlreadyExists(Exception):
    response = {"Error": {"Code": "PreconditionFailed"}}


class MemoryS3:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.write_times: dict[str, datetime] = {}
        self.written_at = datetime(2026, 4, 9, 22, 20, tzinfo=UTC)
        self.listed_bytes_override: int | None = None

    def put_object(self, *, Bucket: str, Key: str, Body: bytes,
                   Metadata: dict[str, str], IfNoneMatch: str) -> None:
        assert Bucket == "private-risk-research"
        assert IfNoneMatch == "*"
        if Key in self.objects:
            raise AlreadyExists
        self.objects[Key] = Body, Metadata["sha256"]
        self.write_times[Key] = self.written_at

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        body, digest = self.objects[Key]
        return {"ContentLength": len(body), "Metadata": {"sha256": digest},
                "LastModified": self.write_times[Key]}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        return {"Body": io.BytesIO(self.objects[Key][0])}

    def list_objects_v2(self, *, Bucket: str,
                        ContinuationToken: str | None = None,
                        Prefix: str | None = None) -> dict[str, object]:
        assert Bucket == "private-risk-research"
        assert ContinuationToken is None
        if self.listed_bytes_override is not None:
            return {"Contents": [{"Size": self.listed_bytes_override}]}
        return {"Contents": [{"Size": len(body), "Key": key,
                               "LastModified": self.write_times[key]}
                              for key, (body, _) in self.objects.items()
                              if Prefix is None or key.startswith(Prefix)]}


def test_latest_private_capture_audits_remote_bytes_without_exposing_key(tmp_path) -> None:
    manifest, raw_root = _manifest(tmp_path, full_history=True)
    client = MemoryS3()
    recorded_at = (datetime.fromisoformat(json.loads(manifest.read_text())["prices"][0]["capture"])
                   + timedelta(hours=1))
    client.written_at = recorded_at
    first = archive_capture(manifest, raw_root=raw_root, s3=client,
                            bucket="private-risk-research", prefix="research",
                            prediction_at=recorded_at, receipt_clock=lambda: recorded_at)
    checked = latest_capture(client, bucket="private-risk-research", prefix="research")
    assert checked["capture_index_count"] == 1
    assert checked["forecast_count"] == 2
    assert first["index_key"] not in json.dumps(checked)
    source = json.loads(client.objects[first["index_key"]][0])["source_objects"][0]["key"]
    data, digest = client.objects[source]
    client.objects[source] = data + b"tampered", digest
    with pytest.raises(ValueError, match="readback hash"):
        latest_capture(client, bucket="private-risk-research", prefix="research")


def test_latest_private_capture_requires_complete_listing_and_valid_timestamp() -> None:
    class IncompleteListing:
        def list_objects_v2(self, **kwargs):
            return {"IsTruncated": True, "Contents": [], "NextContinuationToken": ""}

    with pytest.raises(ValueError, match="listing"):
        latest_capture(IncompleteListing(), bucket="private-risk-research", prefix="research")
    with pytest.raises(ValueError, match="no archive"):
        latest_capture(MemoryS3(), bucket="private-risk-research", prefix="research")


def test_capture_preflight_skips_existing_origin_and_rejects_corruption(tmp_path) -> None:
    manifest, raw_root = _manifest(tmp_path, full_history=True)
    client = MemoryS3()
    origin = nasdaq_sessions(date(2026, 1, 2), date(2026, 9, 30))[:125][-1].session_date
    assert capture_due(client, bucket="private-risk-research", prefix="research", end=origin)
    recorded_at = (datetime.fromisoformat(json.loads(manifest.read_text())["prices"][0]["capture"])
                   + timedelta(hours=1))
    client.written_at = recorded_at
    archived = archive_capture(manifest, raw_root=raw_root, s3=client,
                               bucket="private-risk-research", prefix="research",
                               prediction_at=recorded_at, receipt_clock=lambda: recorded_at)
    assert not capture_due(client, bucket="private-risk-research", prefix="research",
                           end=origin + timedelta(days=1))
    index = json.loads(client.objects[archived["index_key"]][0])
    source = index["source_objects"][0]["key"]
    body, digest = client.objects[source]
    client.objects[source] = body + b"tampered", digest
    with pytest.raises(ValueError, match="readback hash"):
        capture_due(client, bucket="private-risk-research", prefix="research", end=origin)


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
    assert audit_capture(client, bucket="private-risk-research", index_key=index_key)[
        "forecast_count"] == 0
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
    client.written_at = recorded_at
    first = archive_capture(manifest, raw_root=raw_root, s3=client,
                            bucket="private-risk-research", prefix="research",
                            prediction_at=recorded_at,
                            receipt_clock=lambda: recorded_at)
    assert first["status"] == "forward_forecasts_archived"
    index = json.loads(client.objects[first["index_key"]][0])
    assert len(index["forecasts"]) == 2
    assert all(len(item["horizons"]) == 2 for item in index["forecasts"])
    checked = audit_capture(client, bucket="private-risk-research",
                            index_key=first["index_key"])
    assert checked["status"] == "archive_readback_verified"
    assert checked["source_object_count"] == 7
    assert checked["forecast_count"] == 2
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


def test_archive_audit_rejects_changed_source_and_late_index(tmp_path) -> None:
    manifest, raw_root = _manifest(tmp_path, full_history=True)
    client = MemoryS3()
    capture = datetime.fromisoformat(json.loads(manifest.read_text())["prices"][0]["capture"])
    recorded_at = capture + timedelta(minutes=5)
    client.written_at = recorded_at
    report = archive_capture(manifest, raw_root=raw_root, s3=client,
                             bucket="private-risk-research", prefix="research",
                             prediction_at=recorded_at, receipt_clock=lambda: recorded_at)
    index = json.loads(client.objects[report["index_key"]][0])
    source_key = index["source_objects"][0]["key"]
    source_bytes, digest = client.objects[source_key]
    client.objects[source_key] = source_bytes + b"x", digest
    with pytest.raises(ValueError, match="readback hash"):
        audit_capture(client, bucket="private-risk-research", index_key=report["index_key"])
    client.objects[source_key] = source_bytes, digest
    client.write_times[source_key] = recorded_at + timedelta(seconds=2)
    client.write_times[report["index_key"]] = recorded_at + timedelta(seconds=3)
    with pytest.raises(ValueError, match="source was stored after prediction"):
        audit_capture(client, bucket="private-risk-research", index_key=report["index_key"])
    client.write_times[source_key] = recorded_at
    next_day = date.fromisoformat(index["forecasts"][0]["horizons"][0]
                                   ["first_outcome_session"])
    client.write_times[report["index_key"]] = datetime.combine(
        next_day, time(10), ZoneInfo("America/New_York")).astimezone(UTC)
    with pytest.raises(ValueError, match="stored after opening"):
        audit_capture(client, bucket="private-risk-research", index_key=report["index_key"])


def test_r2_budget_blocks_upload_before_any_source_write(tmp_path) -> None:
    manifest, raw_root = _manifest(tmp_path)
    client = MemoryS3()
    client.listed_bytes_override = MAX_BUCKET_BYTES - 1
    with pytest.raises(ValueError, match="bucket budget"):
        archive_capture(manifest, raw_root=raw_root, s3=client,
                        bucket="private-risk-research", prefix="research",
                        prediction_at=datetime(2026, 4, 9, 22, 20, tzinfo=UTC),
                        receipt_clock=lambda: datetime(2026, 4, 9, 22, 20, tzinfo=UTC),
                        budget_check=bucket_budget_guard(client, "private-risk-research"))
    assert not client.objects
    with pytest.raises(ValueError, match="per-run budget"):
        bucket_budget_guard(client, "private-risk-research")(MAX_CAPTURE_BYTES + 1)


def test_r2_client_uses_private_endpoint_and_auto_region(monkeypatch) -> None:
    monkeypatch.setenv("SHOCKGRAPH_R2_ACCOUNT_ID", "a" * 32)
    monkeypatch.setenv("SHOCKGRAPH_R2_BUCKET", "private-risk-research")
    monkeypatch.setenv("SHOCKGRAPH_R2_ACCESS_KEY_ID", "test-access")
    monkeypatch.setenv("SHOCKGRAPH_R2_SECRET_ACCESS_KEY", "test-secret")
    arguments = {}

    class FakeBoto3:
        def client(self, service: str, **kwargs):
            arguments.update({"service": service, **kwargs})
            return object()

    monkeypatch.setattr(private_r2.importlib, "import_module", lambda _: FakeBoto3())
    _, bucket = private_r2.configured_r2()
    assert bucket == "private-risk-research"
    assert arguments == {"service": "s3", "region_name": "auto",
                         "endpoint_url": f"https://{'a' * 32}.r2.cloudflarestorage.com",
                         "aws_access_key_id": "test-access",
                         "aws_secret_access_key": "test-secret"}


def test_cli_requires_private_bucket_before_loading_the_archive(monkeypatch, capsys) -> None:
    monkeypatch.delenv("SHOCKGRAPH_R2_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("SHOCKGRAPH_R2_BUCKET", raising=False)
    monkeypatch.delenv("SHOCKGRAPH_R2_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("SHOCKGRAPH_R2_SECRET_ACCESS_KEY", raising=False)
    assert main(["--manifest", "/missing/manifest.json"]) == 2
    assert json.loads(capsys.readouterr().out) == {"status": "private_archive_not_configured"}
    assert audit_main(["--index-key", "private/index.json"]) == 2
    assert json.loads(capsys.readouterr().out) == {"status": "private_archive_not_configured"}

"""Official evaluation coverage counts forecast origins, not R2 objects or models."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from scripts.archive_forward_capture import archive_capture
from scripts.audit_official_evaluation import audit_evaluation_coverage, nonoverlap_count
from tests.integration.test_private_forward_archive import MemoryS3, _manifest


def _archive(client, manifest, root):
    client.written_at = (datetime.fromisoformat(json.loads(manifest.read_text())
                         ["prices"][0]["capture"]) + timedelta(minutes=5))
    return archive_capture(manifest, raw_root=root, s3=client,
                           bucket="private-risk-research", prefix="research",
                           prediction_at=client.written_at,
                           receipt_clock=lambda: client.written_at)


def test_coverage_waits_for_later_price_vintage_and_deduplicates_origin(tmp_path):
    first_manifest, first_root = _manifest(tmp_path / "first", full_history=True)
    later_manifest, later_root = _manifest(tmp_path / "later", full_history=True,
                                          extra_sessions=5)
    client = MemoryS3()
    _archive(client, first_manifest, first_root)
    first = audit_evaluation_coverage(client, bucket="private-risk-research",
                                      prefix="research")
    assert first["unique_origin_count"] == 1
    assert first["horizons"]["5"]["scored_origin_count"] == 0
    assert first["horizons"]["20"]["pending_origin_count"] == 1
    _archive(client, later_manifest, later_root)
    second = audit_evaluation_coverage(client, bucket="private-risk-research",
                                       prefix="research")
    assert second["unique_origin_count"] == 2
    assert second["horizons"]["5"]["scored_origin_count"] == 1
    assert second["horizons"]["5"]["nonoverlapping_origin_count"] == 1
    assert second["horizons"]["20"]["scored_origin_count"] == 0
    assert second["public_performance_allowed"] is False


def test_nonoverlap_uses_outcome_interval_not_asset_or_row_count():
    assert nonoverlap_count(((1, 5), (2, 6), (6, 10), (11, 15))) == 3
    assert nonoverlap_count(()) == 0
    with pytest.raises(ValueError, match="window"):
        nonoverlap_count(((5, 1),))


def test_coverage_rejects_tampered_archived_origin(tmp_path):
    manifest, root = _manifest(tmp_path, full_history=True)
    client = MemoryS3()
    archived = _archive(client, manifest, root)
    key = archived["index_key"]
    body, sha = client.objects[key]
    client.objects[key] = body + b"tampered", sha
    with pytest.raises(ValueError, match="readback hash"):
        audit_evaluation_coverage(client, bucket="private-risk-research",
                                  prefix="research")


def test_coverage_does_not_turn_duplicate_capture_into_a_second_origin(tmp_path):
    manifest, root = _manifest(tmp_path, full_history=True)
    client = MemoryS3()
    _archive(client, manifest, root)
    client.written_at += timedelta(seconds=2)
    archive_capture(manifest, raw_root=root, s3=client,
                    bucket="private-risk-research", prefix="research",
                    prediction_at=client.written_at,
                    receipt_clock=lambda: client.written_at)
    report = audit_evaluation_coverage(client, bucket="private-risk-research",
                                       prefix="research")
    assert report["audited_index_count"] == 2
    assert report["unique_origin_count"] == 1
    assert report["duplicate_forecast_index_count"] == 1

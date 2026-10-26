"""The R2 to PostgreSQL bridge must not trust a stored score without readback."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from scripts.archive_forward_capture import archive_capture
from scripts.persist_official_scores import persist_official_metadata
from tests.integration.test_private_forward_archive import MemoryS3, _manifest
from tests.unit.test_official_score_metadata import MemoryCursor


class MemoryConnection:
    def __init__(self) -> None:
        self.cursor_value = MemoryCursor()
        self.commits = 0
        self.rollbacks = 0

    def transaction(self):
        connection = self

        class Transaction:
            def __enter__(self):
                self.before = connection.cursor_value.rows.copy()
                return connection

            def __exit__(self, exc_type, exc_value, traceback):
                if exc_type is None:
                    connection.commits += 1
                else:
                    connection.cursor_value.rows = self.before
                    connection.rollbacks += 1

        return Transaction()

    def cursor(self):
        return self.cursor_value


def _mature_archive(tmp_path):
    first_manifest, first_root = _manifest(tmp_path / "first", full_history=True)
    label_manifest, label_root = _manifest(tmp_path / "label", full_history=True,
                                           extra_sessions=5)
    client = MemoryS3()
    for manifest, root in ((first_manifest, first_root), (label_manifest, label_root)):
        import json

        client.written_at = (datetime.fromisoformat(json.loads(manifest.read_text())
                            ["prices"][0]["capture"]) + timedelta(minutes=5))
        archive_capture(manifest, raw_root=root, s3=client,
                        bucket="private-risk-research", prefix="research",
                        prediction_at=client.written_at, receipt_clock=lambda: client.written_at)
    return client


def test_bridge_writes_verified_first_score_and_retries_without_new_rows(tmp_path):
    client = _mature_archive(tmp_path)
    connection = MemoryConnection()
    result = persist_official_metadata(client, connection, bucket="private-risk-research",
                                       prefix="research")
    assert result == {"status": "private_official_metadata_verified", "score_count": 2,
                      "new_row_count": 8, "public_performance_allowed": False}
    assert len(connection.cursor_value.rows) == 8
    assert persist_official_metadata(client, connection, bucket="private-risk-research",
                                     prefix="research")["new_row_count"] == 0
    assert connection.commits == 2


def test_bridge_rejects_changed_score_bytes_without_db_writes(tmp_path):
    client = _mature_archive(tmp_path)
    connection = MemoryConnection()
    from scripts.score_archived_forward import run_official_scores

    run_official_scores(client, bucket="private-risk-research", prefix="research")
    key = next(key for key in client.objects if "/scores/" in key)
    original, digest = client.objects[key]
    client.objects[key] = original + b"tampered", digest
    with pytest.raises(ValueError, match="immutable object collision|score artifact"):
        persist_official_metadata(client, connection, bucket="private-risk-research",
                                  prefix="research")
    assert not connection.cursor_value.rows
    assert connection.commits == 0


def test_bridge_fails_closed_on_existing_different_metadata(tmp_path):
    client = _mature_archive(tmp_path)
    connection = MemoryConnection()
    persist_official_metadata(client, connection, bucket="private-risk-research",
                              prefix="research")
    first_key = next(iter(connection.cursor_value.rows))
    saved = connection.cursor_value.rows[first_key]
    connection.cursor_value.rows[first_key] = (*saved[:-1], True)
    with pytest.raises(ValueError, match="conflict"):
        persist_official_metadata(client, connection, bucket="private-risk-research",
                                  prefix="research")
    assert connection.rollbacks == 1
    assert connection.cursor_value.rows[first_key][-1] is True

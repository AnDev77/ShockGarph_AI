"""Synthetic checks for Kafka draft handoff without a broker or paid LLM call."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from shockgraph_briefing.filings import FilingCapture
from shockgraph_briefing.kafka_jobs import (
    DraftJob,
    consume_once,
    enqueue,
    job_id,
    process_job,
    relay,
)
from shockgraph_briefing.pipeline import (
    CaptureStatus,
    Claim,
    Draft,
    Evidence,
    Summary,
    read_artifact,
    write_artifact,
)

NOW = datetime(2026, 11, 16, 12, tzinfo=UTC)
MODEL = "synthetic-model"
SOURCE = hashlib.sha256(b"synthetic filing").hexdigest()


def capture(directory: Path, *, source: str = SOURCE, age: int = 1) -> None:
    filing = FilingCapture(
        accession="0001178913-26-005000",
        document="report.htm",
        form="6-K",
        accepted_at=NOW - timedelta(days=age),
        fetched_at=NOW,
        sha256=source,
        blocks=[
            "Illustrative revenue for this quarter is shown in this synthetic paragraph.",
            "Management expects a synthetic change in the forward outlook.",
        ],
    )
    write_artifact(
        directory / "capture-camt.json",
        CaptureStatus(checked_at=NOW, status="ok", filing=filing),
    )


def summary(chunks: list[Evidence]) -> Summary:
    return Summary(
        summary=[Claim(text="합성 공시의 매출을 설명합니다.", evidence_ids=[chunks[0].id])]
    )


class Producer:
    def __init__(self, error: object = None) -> None:
        self.error = error
        self.messages: list[tuple[str, bytes, bytes]] = []

    def produce(self, topic: str, *, key: bytes, value: bytes, on_delivery: Any) -> None:
        self.messages.append((topic, key, value))
        on_delivery(self.error, object())

    def flush(self, timeout: float) -> int:
        assert timeout > 0
        return 0


class Message:
    def __init__(self, key: bytes, value: bytes) -> None:
        self._key = key
        self._value = value

    def key(self) -> bytes:
        return self._key

    def value(self) -> bytes:
        return self._value

    def error(self) -> None:
        return None


class Consumer:
    def __init__(self, message: Message) -> None:
        self.message = message
        self.commits = 0

    def poll(self, timeout: float) -> Message:
        assert timeout > 0
        return self.message

    def commit(self, *, message: Message, asynchronous: bool) -> None:
        assert message is self.message and asynchronous is False
        self.commits += 1


def test_intent_precedes_delivery_and_duplicate_is_noop(tmp_path: Path) -> None:
    capture(tmp_path)
    job = enqueue(tmp_path, model=MODEL, now=NOW)
    assert job.id == job_id(SOURCE, MODEL)
    assert enqueue(tmp_path, model=MODEL, now=NOW).id == job.id
    assert not (tmp_path / "sent-camt.json").exists()
    producer = Producer()
    assert relay(tmp_path, producer)
    assert not relay(tmp_path, producer)
    assert len(producer.messages) == 1
    topic, key, value = producer.messages[0]
    assert topic == "shockgraph.briefing.draft.v1"
    assert key == job.id.encode()
    assert DraftJob.model_validate_json(value) == job
    assert SOURCE.encode() in value
    assert b"revenue" not in value and b"OPENAI_API_KEY" not in value


def test_failed_delivery_keeps_intent_and_new_capture_waits(tmp_path: Path) -> None:
    capture(tmp_path)
    enqueue(tmp_path, model=MODEL, now=NOW)
    with pytest.raises(RuntimeError, match="acknowledged"):
        relay(tmp_path, Producer(error="broker unavailable"))
    assert not (tmp_path / "sent-camt.json").exists()
    capture(tmp_path, source="a" * 64)
    with pytest.raises(ValueError, match="previous"):
        enqueue(tmp_path, model=MODEL, now=NOW)
    assert relay(tmp_path, Producer())
    new = enqueue(tmp_path, model=MODEL, now=NOW)
    assert new.source_sha256 == "a" * 64


def test_consumer_commits_after_draft_and_does_not_recall_model(tmp_path: Path) -> None:
    capture(tmp_path)
    event = enqueue(tmp_path, model=MODEL, now=NOW)
    message = Message(event.id.encode(), event.model_dump_json().encode())
    consumer = Consumer(message)
    calls: list[int] = []

    def generate(chunks: list[Evidence]) -> Summary:
        calls.append(1)
        return summary(chunks)

    assert consume_once(tmp_path, consumer, model=MODEL, now=NOW, generate=generate)
    assert consume_once(tmp_path, consumer, model=MODEL, now=NOW, generate=generate)
    assert calls == [1]
    assert consumer.commits == 2
    draft = Draft.model_validate_json(read_artifact(tmp_path / "draft-camt.json"))
    assert draft.source_sha256 == SOURCE
    assert not (tmp_path / "reviewed-camt.json").exists()


def test_wrong_key_source_and_stale_capture_do_not_commit(tmp_path: Path) -> None:
    capture(tmp_path)
    event = enqueue(tmp_path, model=MODEL, now=NOW)
    raw = event.model_dump_json().encode()
    consumer = Consumer(Message(b"wrong", raw))
    with pytest.raises(ValueError, match="key"):
        consume_once(tmp_path, consumer, model=MODEL, now=NOW, generate=summary)
    assert consumer.commits == 0
    capture(tmp_path, source="b" * 64)
    write_artifact(
        tmp_path / f"capture-{SOURCE}.json",
        CaptureStatus.model_validate_json(read_artifact(tmp_path / "capture-camt.json")),
    )
    with pytest.raises(ValueError, match="source"):
        consume_once(
            tmp_path, Consumer(Message(event.id.encode(), raw)),
            model=MODEL, now=NOW, generate=summary
        )
    capture(tmp_path, age=8)
    write_artifact(
        tmp_path / f"capture-{SOURCE}.json",
        CaptureStatus.model_validate_json(read_artifact(tmp_path / "capture-camt.json")),
    )
    with pytest.raises(ValueError, match="eligible"):
        process_job(raw, tmp_path, model=MODEL, now=NOW, generate=summary)
    assert not (tmp_path / "draft-camt.json").exists()


def test_event_identity_and_size_are_bounded(tmp_path: Path) -> None:
    capture(tmp_path)
    event = enqueue(tmp_path, model=MODEL, now=NOW)
    with pytest.raises(ValueError, match="identity"):
        DraftJob.model_validate({**event.model_dump(), "id": "0" * 64})
    with pytest.raises(ValueError, match="byte limit"):
        process_job(b"x" * 4097, tmp_path, model=MODEL, now=NOW, generate=summary)


def test_older_job_uses_immutable_snapshot_after_new_capture(tmp_path: Path) -> None:
    capture(tmp_path)
    old = enqueue(tmp_path, model=MODEL, now=NOW)
    assert relay(tmp_path, Producer())
    capture(tmp_path, source="c" * 64)
    enqueue(tmp_path, model=MODEL, now=NOW)
    assert process_job(old.model_dump_json().encode(), tmp_path, model=MODEL, now=NOW,
                       generate=summary)
    assert (tmp_path / f"draft-{old.id}.json").exists()
    assert not (tmp_path / "draft-camt.json").exists()

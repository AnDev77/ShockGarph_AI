"""Kafka handoff for reviewed CAMT briefing drafts.

The local job file is an operator-replayable intent, not a transactional database outbox.
Kafka carries a reference and hash, never filing text, credentials, or model output.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import os
import sys
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints, model_validator

from .filings import FilingCapture
from .pipeline import (
    PROMPT_VERSION,
    CaptureStatus,
    Draft,
    Evidence,
    Summary,
    Window,
    _check_draft,
    make_draft,
    openai_summary,
    read_artifact,
    utc_now,
    write_artifact,
)

TOPIC = "shockgraph.briefing.draft.v1"
GROUP = "shockgraph-briefing-draft-v1"
MAX_EVENT_BYTES = 4096
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


def job_id(source_sha256: str, model: str) -> str:
    return hashlib.sha256(
        (PROMPT_VERSION + ":" + source_sha256 + ":" + model).encode()
    ).hexdigest()


class DraftJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    id: Digest
    symbol: Literal["CAMT"] = "CAMT"
    source_sha256: Digest
    model: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    requested_at: AwareDatetime

    @model_validator(mode="after")
    def valid_id(self) -> DraftJob:
        if self.id != job_id(self.source_sha256, self.model):
            raise ValueError("Draft job identity does not match source and model")
        return self


def eligible_capture(directory: Path, *, now: datetime, source: str | None = None) -> FilingCapture:
    path = directory / (f"capture-{source}.json" if source else "capture-camt.json")
    capture = CaptureStatus.model_validate_json(read_artifact(path))
    if (
        capture.status != "ok"
        or capture.filing is None
        or not now - timedelta(days=1) <= capture.checked_at <= now
        or not now - Window <= capture.filing.accepted_at <= now
    ):
        raise ValueError("No current and eligible CAMT filing")
    return capture.filing


def enqueue(directory: Path, *, model: str, now: datetime) -> DraftJob:
    """Write intent before any Kafka delivery. Repeated calls reuse the same identity."""
    filing = eligible_capture(directory, now=now)
    snapshot = directory / f"capture-{filing.sha256}.json"
    if snapshot.exists():
        captured = eligible_capture(directory, now=now, source=filing.sha256)
        if captured.model_dump(exclude={"fetched_at"}) != filing.model_dump(
            exclude={"fetched_at"}
        ):
            raise ValueError("Immutable capture snapshot differs from current source")
    else:
        write_artifact(
            snapshot,
            CaptureStatus.model_validate_json(read_artifact(directory / "capture-camt.json")),
        )
    job = DraftJob(
        id=job_id(filing.sha256, model),
        source_sha256=filing.sha256,
        model=model,
        requested_at=now,
    )
    path = directory / "job-camt.json"
    try:
        previous = DraftJob.model_validate_json(read_artifact(path))
    except FileNotFoundError:
        previous = None
    if previous is not None:
        if previous.id == job.id:
            return previous
        try:
            sent = DraftJob.model_validate_json(read_artifact(directory / "sent-camt.json"))
        except FileNotFoundError:
            sent = None
        if sent is None or sent.id != previous.id:
            raise ValueError("Deliver the previous job before replacing its intent")
    write_artifact(path, job)
    return job


def relay(directory: Path, producer: Any, *, topic: str = TOPIC) -> bool:
    """A lost acknowledgement can cause redelivery; the consumer checks job identity."""
    job = DraftJob.model_validate_json(read_artifact(directory / "job-camt.json"))
    try:
        sent = DraftJob.model_validate_json(read_artifact(directory / "sent-camt.json"))
    except FileNotFoundError:
        sent = None
    if sent is not None and sent.id == job.id:
        return False
    delivered: list[object] = []

    def acknowledged(error: object, _message: object) -> None:
        delivered.append(error)

    producer.produce(
        topic,
        key=job.id.encode(),
        value=job.model_dump_json().encode(),
        on_delivery=acknowledged,
    )
    remaining = producer.flush(10.0)
    if remaining != 0 or delivered != [None]:
        raise RuntimeError("Kafka delivery was not acknowledged")
    write_artifact(directory / "sent-camt.json", job)
    return True


def process_job(
    data: bytes,
    directory: Path,
    *,
    model: str,
    now: datetime,
    generate: Callable[[list[Evidence]], Summary],
) -> bool:
    """Create an unpublished draft; repeated delivery does not repeat a completed call."""
    if len(data) > MAX_EVENT_BYTES:
        raise ValueError("Kafka event exceeds its byte limit")
    job = DraftJob.model_validate_json(data)
    if job.requested_at > now or job.model != model:
        raise ValueError("Job timestamp or model does not match this worker")
    filing = eligible_capture(directory, now=now, source=job.source_sha256)
    if filing.sha256 != job.source_sha256:
        raise ValueError("Job source does not match the current capture")
    path = directory / f"draft-{job.id}.json"
    try:
        previous = Draft.model_validate_json(read_artifact(path))
    except FileNotFoundError:
        previous = None
    if previous:
        if previous.source_sha256 != job.source_sha256 or previous.model != job.model:
            raise ValueError("Stored draft does not match job")
        _check_draft(previous, filing)
        draft = previous
    else:
        draft = make_draft(filing, generate, model=model, as_of=now)
        write_artifact(path, draft)
    current = DraftJob.model_validate_json(read_artifact(directory / "job-camt.json"))
    if current.id == job.id:
        write_artifact(directory / "draft-camt.json", draft)
    return previous is None


def consume_once(
    directory: Path,
    consumer: Any,
    *,
    model: str,
    now: datetime,
    generate: Callable[[list[Evidence]], Summary],
) -> bool:
    """Commit the offset only after the draft is durable; failures remain retryable."""
    message = consumer.poll(5.0)
    if message is None:
        return False
    if message.error():
        raise RuntimeError("Kafka consumer returned an error")
    raw = message.value()
    if not isinstance(raw, bytes):
        raise ValueError("Kafka event must contain bytes")
    event = DraftJob.model_validate_json(raw)
    if message.key() != event.id.encode():
        raise ValueError("Kafka key and job identity differ")
    process_job(raw, directory, model=model, now=now, generate=generate)
    consumer.commit(message=message, asynchronous=False)
    return True


def _kafka() -> Any:
    try:
        return importlib.import_module("confluent_kafka")
    except ImportError as error:
        raise RuntimeError("Install the optional kafka dependency") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("artifacts/briefing"))
    command = parser.add_subparsers(dest="command", required=True)
    command.add_parser("enqueue")
    command.add_parser("relay")
    worker = command.add_parser("work-once")
    worker.add_argument("--allow-source-transfer", action="store_true", required=True)
    args = parser.parse_args()
    directory: Path = args.directory
    model = os.environ.get("SHOCKGRAPH_BRIEFING_MODEL", "").strip()
    if not model:
        parser.error("Set SHOCKGRAPH_BRIEFING_MODEL")
    if args.command == "enqueue":
        enqueue(directory, model=model, now=utc_now())
        print("CAMT draft job intent recorded")
        return 0
    bootstrap = os.environ.get("SHOCKGRAPH_KAFKA_BOOTSTRAP", "").strip()
    if not bootstrap:
        parser.error("Set SHOCKGRAPH_KAFKA_BOOTSTRAP")
    kafka = _kafka()
    if args.command == "relay":
        producer = kafka.Producer(
            {"bootstrap.servers": bootstrap, "acks": "all", "enable.idempotence": True}
        )
        changed = relay(directory, producer)
        print("CAMT draft job delivered" if changed else "CAMT draft job already delivered")
        return 0
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        parser.error("Set OPENAI_API_KEY for the worker")
    consumer = kafka.Consumer(
        {
            "bootstrap.servers": bootstrap,
            "group.id": GROUP,
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
        }
    )
    try:
        consumer.subscribe([TOPIC])
        with httpx.Client(timeout=25.0) as client:
            consumed = consume_once(
                directory,
                consumer,
                model=model,
                now=utc_now(),
                generate=lambda chunks: openai_summary(
                    chunks, client=client, model=model, api_key=key
                ),
            )
        print("CAMT draft processed" if consumed else "No CAMT draft job")
        return 0
    finally:
        consumer.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, httpx.HTTPError, LookupError, TypeError) as error:
        print("Briefing job failed: " + type(error).__name__, file=sys.stderr)
        raise SystemExit(1) from error

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ObjectReference:
    key: str
    uri: str
    sha256: str
    created: bool


class ObjectStore(Protocol):
    def put_json(
        self,
        value: Mapping[str, Any],
        *,
        key: str,
    ) -> ObjectReference: ...


class QueuePublisher(Protocol):
    def publish(self, *, topic: str, message_id: str, payload: Mapping[str, Any]) -> None: ...


class CleanRepository(Protocol):
    def write_once(
        self,
        *,
        idempotency_key: str,
        records: Sequence[Mapping[str, Any]],
        processed_at: datetime,
    ) -> bool: ...

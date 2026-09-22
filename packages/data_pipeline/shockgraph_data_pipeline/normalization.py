from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from shockgraph_data_pipeline.ports import CleanRepository


def normalization_key(
    *, payload_hash: str, transformation_version: str, target_table: str
) -> str:
    identity = f"{payload_hash}:{transformation_version}:{target_table}".encode()
    return hashlib.sha256(identity).hexdigest()


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    idempotency_key: str
    record_count: int
    created: bool


class RawToCleanWriter:
    def __init__(self, repository: CleanRepository) -> None:
        self.repository = repository

    def process(
        self,
        payload: Mapping[str, Any],
        *,
        payload_hash: str,
        transformation_version: str,
        target_table: str,
        transform: Callable[[Mapping[str, Any]], Sequence[Mapping[str, Any]]],
        processed_at: datetime | None = None,
    ) -> NormalizationResult:
        records = tuple(transform(payload))
        key = normalization_key(
            payload_hash=payload_hash,
            transformation_version=transformation_version,
            target_table=target_table,
        )
        created = self.repository.write_once(
            idempotency_key=key,
            records=records,
            processed_at=processed_at or datetime.now(UTC),
        )
        return NormalizationResult(key, len(records), created)


class InMemoryCleanRepository:
    """Deterministic adapter for unit tests and local pipeline development."""

    def __init__(self) -> None:
        self.batches: dict[str, tuple[Mapping[str, Any], ...]] = {}

    def write_once(
        self,
        *,
        idempotency_key: str,
        records: Sequence[Mapping[str, Any]],
        processed_at: datetime,
    ) -> bool:
        del processed_at
        if idempotency_key in self.batches:
            return False
        self.batches[idempotency_key] = tuple(records)
        return True

from __future__ import annotations

from collections.abc import Mapping

from shockgraph_data_pipeline.normalization import InMemoryCleanRepository, RawToCleanWriter


def test_raw_to_clean_writer_is_idempotent_for_same_transformation() -> None:
    repository = InMemoryCleanRepository()
    writer = RawToCleanWriter(repository)

    def transform(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
        return [{"value": payload["value"]}]

    first = writer.process(
        {"value": 42},
        payload_hash="a" * 64,
        transformation_version="asset-price-v1",
        target_table="asset_prices",
        transform=transform,
    )
    second = writer.process(
        {"value": 42},
        payload_hash="a" * 64,
        transformation_version="asset-price-v1",
        target_table="asset_prices",
        transform=transform,
    )

    assert first.created is True
    assert second.created is False
    assert first.idempotency_key == second.idempotency_key
    assert len(repository.batches) == 1


def test_new_transformation_version_creates_new_batch() -> None:
    repository = InMemoryCleanRepository()
    writer = RawToCleanWriter(repository)

    results = [
        writer.process(
            {"value": 42},
            payload_hash="a" * 64,
            transformation_version=version,
            target_table="asset_prices",
            transform=lambda payload: [payload],
        )
        for version in ("v1", "v2")
    ]

    assert all(result.created for result in results)
    assert len(repository.batches) == 2

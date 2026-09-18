from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from shockgraph_data_pipeline.kalshi_contract import iter_market_snapshots, payload_sha256


def test_fixture_can_be_validated_normalized_and_lineage_hashed() -> None:
    fixture = (
        Path(__file__).parents[2] / "data" / "fixtures" / "kalshi" / "events_response.json"
    )
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    observed_at = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

    snapshots = list(iter_market_snapshots(payload, observed_at=observed_at))

    assert snapshots[0].raw_payload_hash == payload_sha256(
        payload["events"][0]["markets"][0]
    )
    assert snapshots[0].observed_at == observed_at
    assert snapshots[0].source == "kalshi"


"""최초 발표·발표 전 컨센서스·동시 자산 가격을 서비스 입력으로 결합한다."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import Field

from shockgraph_analytics.cpi_distribution import ConsensusVintage, ThresholdQuote
from shockgraph_analytics.paper_panel import AssetMinuteBar
from shockgraph_analytics.scenarios import (
    Record,
    ScenarioDataset,
    ScenarioObservation,
    demo_dataset,
)


class ServingRelease(Record):
    event_id: str = Field(min_length=1)
    event_ticker: str = Field(min_length=1)
    release_at: datetime
    actual_mom_first: float
    source_url: str = Field(min_length=1)
    raw_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def build_serving_dataset(
    *,
    releases: list[ServingRelease],
    bars: list[AssetMinuteBar],
    consensuses: list[ConsensusVintage],
    quotes: list[ThresholdQuote],
    target_event_id: str,
    as_of: datetime,
    release_at: datetime,
    source_kind: Literal["synthetic", "licensed_historical"],
    source_reference: str,
    label_timing_policy: Literal["official_release_timestamp_proxy"],
    authorization_reference: str | None = None,
) -> tuple[ScenarioDataset, list[dict[str, Any]]]:
    # The explicit policy records publication-time proxies, not measured reception latency.
    if label_timing_policy != "official_release_timestamp_proxy":
        raise ValueError("unsupported first-release availability policy")
    if (
        len({r.event_id for r in releases}) != len(releases)
        or len({r.event_ticker for r in releases}) != len(releases)
        or len({r.release_at for r in releases}) != len(releases)
    ):
        raise ValueError("duplicate release identity or timestamp")
    by_consensus = {c.event_id: c for c in consensuses}
    by_bar = {(b.asset_id, b.price_at): b for b in bars}
    if len(by_consensus) != len(consensuses) or len(by_bar) != len(bars):
        raise ValueError("duplicate consensus or asset minute bar")
    if target_event_id not in by_consensus:
        raise ValueError("target consensus missing")
    if not quotes or any(q.event_id != target_event_id for q in quotes):
        raise ValueError("target quote event mismatch")
    observations = []
    coverage = []
    for event in releases:
        row: dict[str, Any] = {"event_id": event.event_id, "status": "eligible"}
        coverage.append(row)
        if event.event_ticker == target_event_id:
            row["status"] = "target_event"
            continue
        if event.release_at >= as_of:
            row["status"] = "not_historical"
            continue
        consensus = by_consensus.get(event.event_ticker)
        if consensus is None:
            row["status"] = "missing_consensus"
            continue
        if consensus.available_at >= event.release_at:
            row["status"] = "late_consensus"
            continue
        if source_kind == "licensed_historical" and not event.source_url.startswith(
            "https://www.bls.gov/news.release/archives/cpi_"
        ):
            raise ValueError("historical actual requires an archived first-release source")
        selected: list[AssetMinuteBar] = []
        returns: dict[str, float] = {}
        missing = []
        for asset in ("SPY", "TLT"):
            start = by_bar.get((asset, event.release_at - timedelta(minutes=1)))
            for horizon, minutes in (("m5", 5), ("m30", 30)):
                end = by_bar.get((asset, event.release_at + timedelta(minutes=minutes)))
                if start is None or end is None:
                    missing.append(f"{asset}:{horizon}")
                    continue
                selected.extend([start, end])
                returns[f"{asset}:{horizon}"] = end.close / start.close - 1
        if missing:
            row.update(status="missing_price", missing_groups=missing)
            continue
        if any(not b.extended_hours for b in selected):
            row["status"] = "price_session_mismatch"
            continue
        available = max(b.available_at for b in selected)
        if available > as_of:
            row["status"] = "returns_not_available"
            continue
        evidence = [event.raw_hash, consensus.raw_hash, *[b.raw_hash for b in selected]]
        digest = hashlib.sha256(json.dumps(evidence, separators=(",", ":")).encode()).hexdigest()
        observations.append(
            ScenarioObservation(
                event_id=event.event_ticker,
                release_at=event.release_at,
                consensus_available_at=consensus.available_at,
                outcome_available_at=event.release_at,
                returns_available_at=available,
                consensus_mom=consensus.expected_mom,
                actual_mom=event.actual_mom_first,
                returns=returns,
                raw_hash=digest,
            )
        )
    dataset = ScenarioDataset(
        source_kind=source_kind,
        source_reference=source_reference,
        publication_authorized=source_kind == "licensed_historical"
        and bool(authorization_reference),
        authorization_reference=authorization_reference,
        as_of=as_of,
        release_at=release_at,
        consensus=by_consensus[target_event_id],
        quotes=quotes,
        observations=observations,
    )
    return dataset, coverage


def demo_inputs() -> dict[str, Any]:
    """외부 API를 사용하지 않는 독립 합성 입력. 실측 자료의 대체가 아니다."""
    dataset = demo_dataset()
    releases = []
    consensuses = [dataset.consensus]
    bars = []
    for event in dataset.observations:
        releases.append(
            ServingRelease(
                event_id=event.event_id,
                event_ticker=event.event_id,
                release_at=event.release_at,
                actual_mom_first=event.actual_mom,
                source_url=f"https://example.invalid/synthetic/{event.event_id}",
                raw_hash=event.raw_hash,
            )
        )
        consensuses.append(
            ConsensusVintage(
                event_id=event.event_id,
                expected_mom=event.consensus_mom,
                available_at=event.consensus_available_at,
                source="independent_synthetic_demo",
                raw_hash=event.raw_hash,
            )
        )
        for asset in ("SPY", "TLT"):
            for minutes in (-1, 5, 30):
                close = 100.0 if minutes == -1 else 100 * (1 + event.returns[f"{asset}:m{minutes}"])
                timestamp = event.release_at + timedelta(minutes=minutes)
                bars.append(
                    AssetMinuteBar(
                        asset_id=asset,
                        price_at=timestamp,
                        available_at=timestamp,
                        open=close,
                        high=close,
                        low=close,
                        close=close,
                        volume=100,
                        extended_hours=True,
                        raw_hash=event.raw_hash,
                    )
                )
    return {
        "releases": releases,
        "bars": bars,
        "consensuses": consensuses,
        "quotes": dataset.quotes,
        "target_event_id": dataset.consensus.event_id,
        "as_of": dataset.as_of,
        "release_at": dataset.release_at,
        "source_kind": "synthetic",
        "source_reference": "independent_synthetic_serving_inputs_v1",
        "label_timing_policy": "official_release_timestamp_proxy",
    }

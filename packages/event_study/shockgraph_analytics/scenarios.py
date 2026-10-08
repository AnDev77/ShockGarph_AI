"""컨센서스 대비 과거 반응의 기술통계. 미래 수익률 예측 모델이 아니다."""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shockgraph_analytics.cpi_distribution import (
    ConsensusVintage,
    ThresholdQuote,
    build_threshold_distribution,
    consensus_surprise_probabilities,
)
from shockgraph_analytics.evaluation import quantile

GROUPS = {"SPY:m5", "SPY:m30", "TLT:m5", "TLT:m30"}
SCENARIOS = ("above", "inline", "below")


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    @field_validator("*", mode="after")
    @classmethod
    def utc(cls, value):
        if isinstance(value, datetime) and (
            value.tzinfo is None or value.utcoffset() != timedelta(0)
        ):
            raise ValueError("timestamps must be UTC")
        return value


class ScenarioObservation(Record):
    event_id: str = Field(min_length=1)
    release_at: datetime
    consensus_available_at: datetime
    outcome_available_at: datetime
    returns_available_at: datetime
    consensus_mom: float
    actual_mom: float
    returns: dict[str, float]
    raw_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def timeline(self) -> Self:
        if self.consensus_available_at >= self.release_at:
            raise ValueError("historical consensus must be available before release")
        if self.outcome_available_at < self.release_at:
            raise ValueError("actual cannot be available before release")
        if self.returns_available_at < self.release_at + timedelta(minutes=30):
            raise ValueError("returns must cover the longest observation window")
        if set(self.returns) != GROUPS or any(
            not math.isfinite(v) or v < -1 for v in self.returns.values()
        ):
            raise ValueError("require four finite simple-return groups")
        if any(
            Decimal(str(v)) % Decimal("0.1") != 0 for v in (self.actual_mom, self.consensus_mom)
        ):
            raise ValueError("CPI values must use the declared 0.1 reporting grid")
        return self


class ScenarioDataset(Record):
    schema_version: Literal["cpi-scenario-input-v1"] = "cpi-scenario-input-v1"
    source_kind: Literal["synthetic", "licensed_historical"]
    source_reference: str = Field(min_length=1)
    publication_authorized: bool = False
    authorization_reference: str | None = None
    as_of: datetime
    release_at: datetime
    consensus: ConsensusVintage
    quotes: list[ThresholdQuote]
    observations: list[ScenarioObservation]

    @model_validator(mode="after")
    def validate_dataset(self) -> Self:
        if self.source_kind == "licensed_historical" and (
            not self.publication_authorized or not self.authorization_reference
        ):
            raise ValueError("real data requires documented publication authorization")
        if self.as_of >= self.release_at:
            raise ValueError("as_of must be before the target release")
        if len({o.event_id for o in self.observations}) != len(self.observations):
            raise ValueError("duplicate historical event")
        if len({o.release_at for o in self.observations}) != len(self.observations):
            raise ValueError("duplicate historical release")
        for row in self.observations:
            if (
                row.event_id == self.consensus.event_id
                or max(row.release_at, row.outcome_available_at, row.returns_available_at)
                > self.as_of
            ):
                raise ValueError("history must be fully available by as_of")
        distribution = build_threshold_distribution(self.quotes, as_of=self.as_of)
        consensus_surprise_probabilities(distribution, self.consensus, release_at=self.release_at)
        return self


def scenario_report(
    dataset: ScenarioDataset, *, asset_id: str, horizon: str, min_sample: int = 10
) -> dict[str, Any]:
    group = f"{asset_id}:{horizon}"
    if group not in GROUPS or min_sample < 2:
        raise ValueError("unsupported asset, horizon or sample threshold")
    distribution = build_threshold_distribution(dataset.quotes, as_of=dataset.as_of)
    probabilities = consensus_surprise_probabilities(
        distribution, dataset.consensus, release_at=dataset.release_at
    )
    rows = []
    for scenario in SCENARIOS:
        history = []
        for event in dataset.observations:
            surprise = Decimal(str(event.actual_mom)) - Decimal(str(event.consensus_mom))
            label = "above" if surprise > 0 else "below" if surprise < 0 else "inline"
            if label == scenario:
                history.append(event)
        values = [row.returns[group] for row in history]
        enough = len(values) >= min_sample
        weights = [1 / len(values)] * len(values) if values else []
        rows.append(
            {
                "scenario": scenario,
                "implied_probability": getattr(probabilities, f"probability_{scenario}"),
                "status": "ready" if enough else "insufficient_data",
                "sample_count": len(values),
                "quantiles": {
                    f"q{q}": quantile(values, weights, q / 100) for q in (10, 25, 50, 75, 90)
                }
                if enough
                else None,
                "period_start": min(row.release_at for row in history).isoformat()
                if history
                else None,
                "period_end": max(row.release_at for row in history).isoformat()
                if history
                else None,
            }
        )
    return {
        "schema_version": "cpi-scenario-report-v1",
        "status": "ready",
        "asset_id": asset_id,
        "horizon": horizon,
        "as_of": dataset.as_of.isoformat(),
        "release_at": dataset.release_at.isoformat(),
        "consensus_mom": dataset.consensus.expected_mom,
        "reporting_step": 0.1,
        "minimum_sample_count": min_sample,
        "total_event_count": len(dataset.observations),
        "quantile_method": "inverse_empirical_cdf",
        "interpretation": "historical_distribution_not_forecast",
        "provenance": {
            "source_kind": dataset.source_kind,
            "source_reference": dataset.source_reference,
            "dataset_sha256": hashlib.sha256(dataset.model_dump_json().encode()).hexdigest(),
        },
        "quote_quality": {
            "threshold_count": len(distribution.thresholds),
            "max_isotonic_adjustment": distribution.max_isotonic_adjustment,
            "max_quote_age_minutes": distribution.max_quote_age_minutes,
        },
        "scenarios": rows,
    }


def demo_dataset() -> ScenarioDataset:
    """독립적으로 만든 설명용 자료. Kalshi나 ETF 실측값을 사용하지 않는다."""
    as_of = datetime(2026, 10, 1, 12, 25, tzinfo=UTC)
    digest = hashlib.sha256(b"shockgraph-independent-synthetic-scenarios-v1").hexdigest()
    observations = []
    for index in range(36):
        release = datetime(2022 + index // 12, index % 12 + 1, 12, 13, 30, tzinfo=UTC)
        label = index % 3
        offset = (index // 3 - 5.5) * 0.0018
        values = {
            "SPY:m5": (-0.004, 0.0005, 0.003)[label] + offset * 0.6,
            "SPY:m30": (-0.007, 0.0008, 0.005)[label] + offset,
            "TLT:m5": (-0.005, -0.0003, 0.004)[label] + offset * 0.45,
            "TLT:m30": (-0.008, -0.0005, 0.007)[label] + offset * 0.8,
        }
        observations.append(
            ScenarioObservation(
                event_id=f"synthetic-cpi-{index}",
                release_at=release,
                consensus_available_at=release - timedelta(days=1),
                outcome_available_at=release + timedelta(minutes=1),
                returns_available_at=release + timedelta(minutes=31),
                consensus_mom=0.3,
                actual_mom=(0.4, 0.3, 0.2)[label],
                returns=values,
                raw_hash=digest,
            )
        )
    consensus = ConsensusVintage(
        event_id="synthetic-target-cpi",
        expected_mom=0.3,
        available_at=as_of - timedelta(days=1),
        source="independent_synthetic_demo",
        raw_hash=digest,
    )
    quotes = [
        ThresholdQuote(
            event_id=consensus.event_id,
            market_ticker=f"synthetic-threshold-{threshold}",
            threshold=threshold,
            probability_above=probability,
            observed_at=as_of - timedelta(minutes=1),
            available_at=as_of,
            spread=0.02,
            raw_hash=digest,
        )
        for threshold, probability in [(0.2, 0.75), (0.3, 0.4)]
    ]
    return ScenarioDataset(
        source_kind="synthetic",
        source_reference="independent_synthetic_demo_v1",
        as_of=as_of,
        release_at=as_of + timedelta(minutes=5),
        consensus=consensus,
        quotes=quotes,
        observations=observations,
    )

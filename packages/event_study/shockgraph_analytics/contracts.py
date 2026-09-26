from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Identifier = Annotated[str, Field(min_length=1)]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Finite = Annotated[float, Field(allow_inf_nan=False)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    @field_validator("*", mode="after")
    @classmethod
    def utc_only(cls, value):
        if isinstance(value, datetime) and (
            value.tzinfo is None or value.utcoffset() != timedelta(0)
        ):
            raise ValueError("timestamp must be timezone-aware UTC")
        return value


class Release(Record):
    event_id: Identifier
    prediction_at: datetime
    release_at: datetime
    return_start_at: datetime
    return_end_at: datetime
    outcome_available_at: datetime
    expectation_available_at: datetime
    actual_value: Finite
    expected_value: Finite
    raw_hash: Hash

    @model_validator(mode="after")
    def timeline(self) -> Self:
        if not self.return_start_at <= self.prediction_at < self.release_at < self.return_end_at:
            raise ValueError("require return_start <= prediction < release < return_end")
        if self.outcome_available_at < self.release_at:
            raise ValueError("outcome cannot be available before release")
        return self


class ProbabilitySnapshot(Record):
    event_id: Identifier
    market_ticker: Identifier
    observed_at: datetime
    available_at: datetime
    probability: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    raw_hash: Hash

    @model_validator(mode="after")
    def timeline(self) -> Self:
        if self.available_at < self.observed_at:
            raise ValueError("probability cannot be available before observation")
        return self


class Price(Record):
    asset_id: Identifier
    price_at: datetime
    available_at: datetime
    price: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    raw_hash: Hash

    @model_validator(mode="after")
    def timeline(self) -> Self:
        if self.available_at < self.price_at:
            raise ValueError("price cannot be available before observation")
        return self


class ResearchDataset(Record):
    source_kind: Literal["synthetic", "research"]
    definition: Identifier
    threshold: Finite
    # All probabilities represent actual_value > threshold for this one definition.
    currency: Literal["USD"]
    price_basis: Literal["adjusted_close", "close"]
    assets: tuple[Identifier, ...]
    weights: tuple[Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)], ...]
    evaluation_at: datetime
    releases: tuple[Release, ...]
    snapshots: tuple[ProbabilitySnapshot, ...]
    prices: tuple[Price, ...]
    max_snapshot_age_hours: Annotated[int, Field(ge=1, le=168)] = 48

    @model_validator(mode="after")
    def consistency(self) -> Self:
        if not self.assets or len(set(self.assets)) != len(self.assets):
            raise ValueError("assets must be nonempty and unique")
        if "portfolio" in self.assets:
            raise ValueError("portfolio is a reserved asset identifier")
        if len(self.weights) != len(self.assets) or not math.isclose(
            sum(self.weights), 1.0, abs_tol=1e-9, rel_tol=0
        ):
            raise ValueError("weights must match assets and sum to one")
        events = {row.event_id for row in self.releases}
        if len(events) != len(self.releases):
            raise ValueError("duplicate event")
        if len({(p.asset_id, p.price_at) for p in self.prices}) != len(self.prices):
            raise ValueError("duplicate price; resolve vintages before evaluation")
        if any(p.asset_id not in self.assets for p in self.prices):
            raise ValueError("unknown asset")
        if any(s.event_id not in events for s in self.snapshots):
            raise ValueError("unknown snapshot event")
        keys = {(s.event_id, s.market_ticker, s.observed_at) for s in self.snapshots}
        if len(keys) != len(self.snapshots):
            raise ValueError("duplicate snapshot")
        for event_id in events:
            tickers = {s.market_ticker for s in self.snapshots if s.event_id == event_id}
            if len(tickers) > 1:
                raise ValueError("select one fixed-definition contract per release")
        return self

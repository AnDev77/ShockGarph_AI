from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Probability = Annotated[Decimal, Field(ge=0, le=1)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0)]
PayloadHash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be stored in UTC")
    return value.astimezone(UTC)


class IngestionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class EventRecord(IngestionRecord):
    source: str = Field(min_length=1)
    external_event_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    open_time: datetime
    close_time: datetime
    resolved_time: datetime | None = None
    result: Literal["yes", "no"] | None = None
    status: Literal["unopened", "open", "closed", "settled"]
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "open_time",
        "close_time",
        "resolved_time",
        "created_at",
        "updated_at",
    )
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_time_order(self) -> Self:
        if self.close_time < self.open_time:
            raise ValueError("close_time cannot precede open_time")
        if self.resolved_time is not None and self.resolved_time < self.open_time:
            raise ValueError("resolved_time cannot precede open_time")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        return self


class MarketSnapshotRecord(IngestionRecord):
    event_id: str = Field(min_length=1)
    market_ticker: str = Field(min_length=1)
    observed_at: datetime
    yes_bid: Probability | None = None
    yes_ask: Probability | None = None
    no_bid: Probability | None = None
    no_ask: Probability | None = None
    last_price: Probability | None = None
    volume: NonNegativeDecimal
    open_interest: NonNegativeDecimal
    raw_payload_hash: PayloadHash

    @field_validator("observed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)

    @model_validator(mode="after")
    def validate_quotes(self) -> Self:
        if self.yes_bid is not None and self.yes_ask is not None and self.yes_bid > self.yes_ask:
            raise ValueError("yes bid exceeds yes ask")
        if self.no_bid is not None and self.no_ask is not None and self.no_bid > self.no_ask:
            raise ValueError("no bid exceeds no ask")
        if self.last_price is None and self.yes_bid is None and self.yes_ask is None:
            raise ValueError("at least one market probability is required")
        return self


class OrderBookSnapshotRecord(IngestionRecord):
    event_id: str = Field(min_length=1)
    market_ticker: str = Field(min_length=1)
    observed_at: datetime
    side: Literal["yes", "no"]
    price: Probability
    quantity: NonNegativeDecimal
    level: int = Field(ge=0)
    raw_payload_hash: PayloadHash

    @field_validator("observed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)


class AssetPriceRecord(IngestionRecord):
    source: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    venue: str = Field(min_length=1)
    observed_at: datetime
    session_date: date
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    close: Annotated[Decimal, Field(gt=0)]
    adjusted_close: Annotated[Decimal, Field(gt=0)] | None = None
    volume: NonNegativeDecimal | None = None
    raw_payload_hash: PayloadHash

    @field_validator("observed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)

class FeatureSnapshotRecord(IngestionRecord):
    event_id: str = Field(min_length=1)
    feature_name: str = Field(min_length=1)
    feature_as_of: datetime
    observed_at: datetime
    value: Decimal
    transformation_version: str = Field(min_length=1)
    raw_payload_hash: PayloadHash

    @field_validator("feature_as_of", "observed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)

    @model_validator(mode="after")
    def reject_future_feature(self) -> Self:
        if self.feature_as_of > self.observed_at:
            raise ValueError("feature_as_of cannot follow observed_at")
        return self

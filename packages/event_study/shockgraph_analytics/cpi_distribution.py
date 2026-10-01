"""Kalshi CPI 임계값 계약을 누수 없는 이산 확률분포로 변환한다."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _FrozenRecord(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
        hide_input_in_errors=True,
    )

    @field_validator("*", mode="after")
    @classmethod
    def require_utc(cls, value):
        if isinstance(value, datetime) and (
            value.tzinfo is None or value.utcoffset() != timedelta(0)
        ):
            raise ValueError("timestamp must be timezone-aware UTC")
        return value


class ThresholdQuote(_FrozenRecord):
    """한 시점에 관측된 엄격한 ``CPI MoM > threshold`` 계약 확률."""

    event_id: str = Field(min_length=1)
    market_ticker: str = Field(min_length=1)
    threshold: float
    observed_at: datetime
    available_at: datetime
    probability_above: float = Field(ge=0, le=1)
    spread: float = Field(ge=0, le=1)
    raw_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    relation: Literal["strictly_greater"] = "strictly_greater"
    unit: Literal["percentage_point"] = "percentage_point"

    @model_validator(mode="after")
    def timeline(self) -> Self:
        if self.available_at < self.observed_at:
            raise ValueError("quote cannot be available before observation")
        return self


class ConsensusVintage(_FrozenRecord):
    """발표 전에 보존한 전문가 컨센서스 빈티지."""

    event_id: str = Field(min_length=1)
    expected_mom: float
    available_at: datetime
    source: str = Field(min_length=1)
    raw_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    unit: Literal["percentage_point"] = "percentage_point"


class ThresholdDistribution(_FrozenRecord):
    event_id: str
    as_of: datetime
    market_tickers: tuple[str, ...]
    thresholds: tuple[float, ...]
    raw_probabilities_above: tuple[float, ...]
    probabilities_above: tuple[float, ...]
    bin_probabilities: tuple[float, ...]
    raw_monotone: bool
    max_isotonic_adjustment: float = Field(ge=0)
    max_quote_age_minutes: float = Field(ge=0)
    method: Literal["unweighted_isotonic_l2_v1"] = "unweighted_isotonic_l2_v1"


class ConsensusSurpriseProbabilities(_FrozenRecord):
    event_id: str
    as_of: datetime
    consensus_mom: float
    reporting_step: float = Field(gt=0)
    probability_below: float = Field(ge=0, le=1)
    probability_inline: float = Field(ge=0, le=1)
    probability_above: float = Field(ge=0, le=1)
    method: Literal["exact_adjacent_thresholds_v1"] = "exact_adjacent_thresholds_v1"


def _isotonic_nonincreasing(values: list[float]) -> list[float]:
    """Unweighted L2 projection with the pool-adjacent-violators algorithm."""
    blocks: list[tuple[float, int]] = []
    for value in values:
        blocks.append((value, 1))
        while len(blocks) >= 2:
            left_sum, left_count = blocks[-2]
            right_sum, right_count = blocks[-1]
            if left_sum / left_count >= right_sum / right_count:
                break
            blocks[-2:] = [(left_sum + right_sum, left_count + right_count)]
    fitted: list[float] = []
    for total, count in blocks:
        fitted.extend([total / count] * count)
    return fitted


def build_threshold_distribution(
    quotes: list[ThresholdQuote],
    *,
    as_of: datetime,
    max_quote_age: timedelta = timedelta(minutes=15),
    max_isotonic_adjustment: float = 0.05,
) -> ThresholdDistribution:
    """동일 사건의 누적 임계값 확률을 단조 곡선과 배타적 구간으로 바꾼다."""
    if as_of.tzinfo is None or as_of.utcoffset() != timedelta(0):
        raise ValueError("as_of must be timezone-aware UTC")
    if max_quote_age <= timedelta(0):
        raise ValueError("max_quote_age must be positive")
    if not math.isfinite(max_isotonic_adjustment) or not 0 <= max_isotonic_adjustment <= 1:
        raise ValueError("max_isotonic_adjustment must be between zero and one")
    if not quotes:
        raise ValueError("at least two threshold quotes required")

    for row in quotes:
        if row.observed_at > as_of or row.available_at > as_of:
            raise ValueError("quote observed or available after as_of")
        if as_of - row.observed_at > max_quote_age:
            raise ValueError("stale threshold quote")
    if len(quotes) < 2:
        raise ValueError("at least two threshold quotes required")
    if len({row.event_id for row in quotes}) != 1:
        raise ValueError("threshold quotes must belong to one event")
    if len({Decimal(str(row.threshold)) for row in quotes}) != len(quotes):
        raise ValueError("duplicate threshold")
    if len({row.market_ticker for row in quotes}) != len(quotes):
        raise ValueError("duplicate market ticker")

    ordered = sorted(quotes, key=lambda row: Decimal(str(row.threshold)))
    raw = [row.probability_above for row in ordered]
    fitted = _isotonic_nonincreasing(raw)
    adjustment = max(abs(before - after) for before, after in zip(raw, fitted, strict=True))
    if adjustment > max_isotonic_adjustment + 1e-12:
        raise ValueError("isotonic adjustment exceeds declared limit")

    bins = [
        1 - fitted[0],
        *(left - right for left, right in zip(fitted, fitted[1:], strict=False)),
        fitted[-1],
    ]
    bins = [0.0 if abs(value) < 1e-15 else value for value in bins]
    if any(value < 0 for value in bins) or not math.isclose(
        math.fsum(bins), 1, abs_tol=1e-12, rel_tol=0
    ):
        raise ValueError("derived threshold bins are not a probability partition")

    return ThresholdDistribution(
        event_id=ordered[0].event_id,
        as_of=as_of,
        market_tickers=tuple(row.market_ticker for row in ordered),
        thresholds=tuple(row.threshold for row in ordered),
        raw_probabilities_above=tuple(raw),
        probabilities_above=tuple(fitted),
        bin_probabilities=tuple(bins),
        raw_monotone=all(left >= right for left, right in zip(raw, raw[1:], strict=False)),
        max_isotonic_adjustment=adjustment,
        max_quote_age_minutes=max(
            (as_of - row.observed_at).total_seconds() / 60 for row in ordered
        ),
    )


def consensus_surprise_probabilities(
    distribution: ThresholdDistribution,
    consensus: ConsensusVintage,
    *,
    release_at: datetime,
    reporting_step: float = 0.1,
) -> ConsensusSurpriseProbabilities:
    """한 자리 소수 CPI 격자에서 컨센서스 하회·부합·상회 확률을 계산한다."""
    if release_at.tzinfo is None or release_at.utcoffset() != timedelta(0):
        raise ValueError("release_at must be timezone-aware UTC")
    if distribution.as_of >= release_at:
        raise ValueError("distribution as_of must be strictly before release")
    if consensus.event_id != distribution.event_id:
        raise ValueError("consensus and distribution event must match")
    if consensus.available_at > distribution.as_of:
        raise ValueError("consensus must be available by as_of")
    if not math.isfinite(reporting_step) or reporting_step <= 0:
        raise ValueError("reporting_step must be positive")

    expected = Decimal(str(consensus.expected_mom))
    step = Decimal(str(reporting_step))
    if expected % step != 0:
        raise ValueError("consensus must align with reporting step")
    probabilities = {
        Decimal(str(threshold)): probability
        for threshold, probability in zip(
            distribution.thresholds, distribution.probabilities_above, strict=True
        )
    }
    lower_boundary = expected - step
    if expected not in probabilities or lower_boundary not in probabilities:
        raise ValueError("exact consensus boundaries are unavailable; interpolation is forbidden")

    above = probabilities[expected]
    above_lower_boundary = probabilities[lower_boundary]
    below = 1 - above_lower_boundary
    inline = above_lower_boundary - above
    values = (below, inline, above)
    if any(value < -1e-12 for value in values) or not math.isclose(
        math.fsum(values), 1, abs_tol=1e-12, rel_tol=0
    ):
        raise ValueError("consensus scenarios are not a probability partition")
    return ConsensusSurpriseProbabilities(
        event_id=distribution.event_id,
        as_of=distribution.as_of,
        consensus_mom=consensus.expected_mom,
        reporting_step=reporting_step,
        probability_below=max(0, below),
        probability_inline=max(0, inline),
        probability_above=max(0, above),
    )

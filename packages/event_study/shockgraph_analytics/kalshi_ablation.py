from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shockgraph_analytics.evaluation import paired_interval, scenario_weights, score

GROUPS = ("SPY:m5", "SPY:m30", "TLT:m5", "TLT:m30")


class AblationEvent(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, allow_inf_nan=False, hide_input_in_errors=True
    )

    event_id: str
    release_at: datetime
    quote_at: datetime
    label_available_at: datetime
    probability: float = Field(ge=0, le=1)
    outcome: bool
    returns: dict[str, float]

    @model_validator(mode="after")
    def validate_event(self) -> Self:
        times = (self.release_at, self.quote_at, self.label_available_at)
        if any(t.tzinfo is None or t.utcoffset() != timedelta(0) for t in times):
            raise ValueError("timestamps must be UTC")
        if not timedelta(0) < self.release_at - self.quote_at <= timedelta(minutes=15):
            raise ValueError("quote must be fresh and strictly before release")
        if self.label_available_at < self.release_at + timedelta(minutes=30):
            raise ValueError("label availability must cover the longest outcome window")
        if set(self.returns) != set(GROUPS):
            raise ValueError("each event requires all four primary groups")
        return self


def walk_forward(events: list[AblationEvent], *, min_train: int) -> list[dict[str, Any]]:
    if min_train < 2:
        raise ValueError("min_train must be at least two")
    ordered = sorted(events, key=lambda e: e.release_at)
    if len({e.event_id for e in ordered}) != len(ordered):
        raise ValueError("duplicate event id")
    if len({e.release_at for e in ordered}) != len(ordered):
        raise ValueError("release times must be distinct")
    folds: list[dict[str, Any]] = []
    for current in ordered:
        train = [
            e
            for e in ordered
            if e.release_at < current.quote_at and e.label_available_at <= current.quote_at
        ]
        counts = Counter(e.outcome for e in train)
        fold: dict[str, Any] = {
            "event_id": current.event_id,
            "train_event_ids": [e.event_id for e in train],
        }
        if len(train) < min_train or min(counts[True], counts[False]) < 2:
            fold.update(
                status="skipped",
                reason=(
                    "insufficient_train_events"
                    if len(train) < min_train
                    else "insufficient_scenario_events"
                ),
            )
            folds.append(fold)
            continue
        outcomes = [e.outcome for e in train]
        weights = {
            "historical_frequency": scenario_weights(outcomes, counts[True] / len(train)),
            "kalshi_probability": scenario_weights(outcomes, current.probability),
        }
        # Only past labels construct distributions; current returns enter scoring only.
        fold.update(status="evaluated", scores={})
        for group in GROUPS:
            values = [e.returns[group] for e in train]
            fold["scores"][group] = {
                name: score(values, w, current.returns[group]) for name, w in weights.items()
            }
        folds.append(fold)
    return folds


class GroupComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    historical_crps: float = Field(ge=0)
    kalshi_crps: float = Field(ge=0)
    mean_crps_difference: float
    paired_event_bootstrap95: tuple[float, float]


class EvaluationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["exploratory", "insufficient_test_events"]
    min_train: int = Field(ge=2)
    required_test_events: int = Field(ge=2)
    test_events: int = Field(ge=0)
    skipped_counts: dict[str, int]
    comparison: dict[str, GroupComparison]

    @model_validator(mode="after")
    def gate(self) -> Self:
        enough = self.test_events >= self.required_test_events
        if (self.status == "exploratory") != enough:
            raise ValueError("evaluation status disagrees with sample gate")
        if set(self.comparison) != (set(GROUPS) if enough else set()):
            raise ValueError("comparison must respect sample gate and primary groups")
        return self


class QuoteTimeExclusion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    release_at: datetime
    quote_at: datetime
    reason: Literal["stale_before_release", "at_or_after_release"]


class AblationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["cpi-kalshi-ablation-v1"] = "cpi-kalshi-ablation-v1"
    scope: Literal["historical_frequency_vs_kalshi_not_macro_benchmark"] = (
        "historical_frequency_vs_kalshi_not_macro_benchmark"
    )
    model: Literal["binary_empirical_shrinkage4"] = "binary_empirical_shrinkage4"
    common_events: int = Field(ge=0)
    selection_counts: dict[str, int]
    quote_time_exclusions: list[QuoteTimeExclusion]
    input_sha256: dict[str, str]
    research: EvaluationSummary
    diagnostic: EvaluationSummary
    limitations: list[str]

    @model_validator(mode="after")
    def settings(self) -> Self:
        counts = self.selection_counts
        reasons = {"stale_before_release", "at_or_after_release"}
        if set(counts) != reasons | {
            "input_events",
            "probability_unavailable",
            "incomplete_asset_windows",
            "accepted",
        } or any(v < 0 for v in counts.values()):
            raise ValueError("invalid selection counts")
        if counts["accepted"] != self.common_events or counts["input_events"] != sum(
            v for k, v in counts.items() if k != "input_events"
        ):
            raise ValueError("selection counts must reconcile")
        exclusions = Counter(e.reason for e in self.quote_time_exclusions)
        if any(exclusions[reason] != counts[reason] for reason in reasons):
            raise ValueError("timing exclusions must reconcile")
        if self.research.min_train != 20 or self.diagnostic.min_train != 5:
            raise ValueError("report requires fixed 20/5 training gates")
        for summary in (self.research, self.diagnostic):
            if summary.required_test_events != 10:
                raise ValueError("report requires ten test events")
            if summary.test_events + sum(summary.skipped_counts.values()) != self.common_events:
                raise ValueError("fold counts must match common events")
        return self


def summarize(events: list[AblationEvent], *, min_train: int) -> EvaluationSummary:
    folds = walk_forward(events, min_train=min_train)
    valid = [f for f in folds if f["status"] == "evaluated"]
    comparison: dict[str, GroupComparison] = {}
    if len(valid) >= 10:
        for group in GROUPS:
            baseline = [f["scores"][group]["historical_frequency"]["crps"] for f in valid]
            kalshi = [f["scores"][group]["kalshi_probability"]["crps"] for f in valid]
            differences = [k - b for k, b in zip(kalshi, baseline, strict=True)]
            interval = paired_interval(differences)
            assert interval is not None
            comparison[group] = GroupComparison(
                historical_crps=math.fsum(baseline) / len(valid),
                kalshi_crps=math.fsum(kalshi) / len(valid),
                mean_crps_difference=math.fsum(differences) / len(valid),
                paired_event_bootstrap95=(interval[0], interval[1]),
            )
    return EvaluationSummary(
        status="exploratory" if len(valid) >= 10 else "insufficient_test_events",
        min_train=min_train,
        required_test_events=10,
        test_events=len(valid),
        skipped_counts=dict(Counter(f["reason"] for f in folds if f["status"] == "skipped")),
        comparison=comparison,
    )

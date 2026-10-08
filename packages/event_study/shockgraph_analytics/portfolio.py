"""사건별 공동수익률의 시장확률 혼합. 검증된 예측 정확도를 뜻하지 않는다."""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Self

from pydantic import Field, model_validator

from shockgraph_analytics.evaluation import quantile
from shockgraph_analytics.scenarios import Record, ScenarioDataset, scenario_report


class PortfolioWeights(Record):
    spy: float = Field(ge=0, le=1)
    tlt: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def total(self) -> Self:
        if Decimal(str(self.spy)) + Decimal(str(self.tlt)) != Decimal(1):
            raise ValueError("portfolio weights must sum to one; no renormalization")
        return self


def portfolio_report(
    dataset: ScenarioDataset,
    *,
    weights: PortfolioWeights,
    horizon: str,
    min_sample: int = 10,
    portfolio_value: float | None = None,
) -> dict[str, Any]:
    if horizon not in ("m5", "m30") or min_sample < 2:
        raise ValueError("unsupported horizon or sample threshold")
    if portfolio_value is not None and (
        not math.isfinite(portfolio_value) or not 0 <= portfolio_value <= 1e12
    ):
        raise ValueError("require finite nonnegative USD valuation up to 1e12")
    reference = scenario_report(dataset, asset_id="SPY", horizon=horizon, min_sample=min_sample)
    grouped = {row["scenario"]: [] for row in reference["scenarios"]}
    for event in dataset.observations:
        difference = Decimal(str(event.actual_mom)) - Decimal(str(event.consensus_mom))
        label = "above" if difference > 0 else "below" if difference < 0 else "inline"
        grouped[label].append(event)
    allocations = {"SPY": weights.spy, "TLT": weights.tlt}
    portfolio_samples = {
        scenario: [
            float(
                sum(
                    Decimal(str(weight)) * Decimal(str(event.returns[f"{asset}:{horizon}"]))
                    for asset, weight in allocations.items()
                )
            )
            for event in events
        ]
        for scenario, events in grouped.items()
    }
    scenario_rows = [
        {
            **row,
            "quantiles": {
                f"q{q}": quantile(
                    portfolio_samples[row["scenario"]],
                    [1 / row["sample_count"]] * row["sample_count"],
                    q / 100,
                )
                for q in (10, 25, 50, 75, 90)
            }
            if row["status"] == "ready"
            else None,
        }
        for row in reference["scenarios"]
    ]
    base = {
        "schema_version": "cpi-portfolio-report-v1",
        "status": "ready",
        "horizon": horizon,
        "weights": allocations,
        "portfolio_value_usd": portfolio_value,
        "currency": "USD",
        "as_of": reference["as_of"],
        "release_at": reference["release_at"],
        "consensus_mom": reference["consensus_mom"],
        "provenance": reference["provenance"],
        "quote_quality": reference["quote_quality"],
        "total_event_count": reference["total_event_count"],
        "minimum_sample_count": min_sample,
        "period_start": min((o.release_at.isoformat() for o in dataset.observations), default=None),
        "period_end": max((o.release_at.isoformat() for o in dataset.observations), default=None),
        "interpretation": "market_weighted_historical_joint_distribution",
        "quantile_method": "inverse_empirical_cdf",
        "performance_status": "not_established",
        "scenarios": scenario_rows,
        "unavailable_probability_mass": math.fsum(
            row["implied_probability"]
            for row in reference["scenarios"]
            if row["sample_count"] < min_sample
        ),
        "result": None,
        "assets": [],
    }
    # A missing positive-probability scenario must never be dropped and renormalized.
    if base["unavailable_probability_mass"] > 0:
        base.update(
            status="insufficient_data", reason="positive_probability_scenario_sample_shortfall"
        )
        return base
    values: list[float] = []
    masses: list[float] = []
    asset_values: dict[str, list[float]] = {"SPY": [], "TLT": []}
    for scenario in reference["scenarios"]:
        probability = scenario["implied_probability"]
        if probability == 0:
            continue
        history = grouped[scenario["scenario"]]
        for event, value in zip(history, portfolio_samples[scenario["scenario"]], strict=True):
            values.append(value)
            masses.append(probability / len(history))
            for asset in asset_values:
                asset_values[asset].append(event.returns[f"{asset}:{horizon}"])
    mean = math.fsum(value * mass for value, mass in zip(values, masses, strict=True))
    quantiles = {f"q{q}": quantile(values, masses, q / 100) for q in (10, 25, 50, 75, 90)}
    base["result"] = {
        "expected_return": mean,
        "probability_up": math.fsum(m for r, m in zip(values, masses, strict=True) if r > 0),
        "probability_down": math.fsum(m for r, m in zip(values, masses, strict=True) if r < 0),
        "probability_flat": math.fsum(m for r, m in zip(values, masses, strict=True) if r == 0),
        "quantiles": quantiles,
        "expected_change_usd": mean * portfolio_value if portfolio_value is not None else None,
        "amount_range_usd": [quantiles["q10"] * portfolio_value, quantiles["q90"] * portfolio_value]
        if portfolio_value is not None
        else None,
    }
    base["assets"] = [
        {
            "asset_id": asset,
            "weight": base["weights"][asset],
            "expected_return": math.fsum(r * m for r, m in zip(returns, masses, strict=True)),
            "return_contribution": base["weights"][asset]
            * math.fsum(r * m for r, m in zip(returns, masses, strict=True)),
        }
        for asset, returns in asset_values.items()
    ]
    return base

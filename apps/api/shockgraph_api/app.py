from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from shockgraph_analytics.kalshi_ablation import AblationReport
from shockgraph_analytics.portfolio import PortfolioWeights, portfolio_report
from shockgraph_analytics.scenarios import ScenarioDataset, demo_dataset, scenario_report

ASSETS = ("SPY", "TLT", "GLD")
HORIZONS = ("m5", "m30")


class ProbabilityMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, allow_inf_nan=False)

    eligible_events: int = Field(ge=0)
    comparable_events: int = Field(ge=0)
    raw_market_brier: float = Field(ge=0, le=1)
    expanding_historical_brier: float = Field(ge=0, le=1)
    mean_brier_difference: float
    paired_event_bootstrap95: tuple[float, float]

    @model_validator(mode="after")
    def validate_comparison(self) -> ProbabilityMetrics:
        lower, upper = self.paired_event_bootstrap95
        if lower > upper or self.comparable_events > self.eligible_events:
            raise ValueError("invalid probability comparison")
        expected = self.raw_market_brier - self.expanding_historical_brier
        if not math.isclose(expected, self.mean_brier_difference, abs_tol=0.00015):
            raise ValueError("inconsistent Brier difference")
        return self


class ResearchSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    schema_version: Literal["paper-event-v1"]
    series_ticker: Literal["KXCPI"]
    event_count: int = Field(ge=0)
    source_checked_at: str
    event_probability_comparison: ProbabilityMetrics


class RecordedSummary(BaseModel):
    """기존 문서의 반올림 집계이며 원본에서 재계산한 스냅샷과 구분한다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["cpi-probability-recorded-v1"]
    as_of: str
    source_document: Literal["docs/cpi-coverage-review.md"]
    decimal_places: Literal[4]
    recomputed: Literal[False]
    metrics: ProbabilityMetrics


def _probability_finding(metrics: ProbabilityMetrics) -> str:
    lower, upper = metrics.paired_event_bootstrap95
    if metrics.comparable_events == 0:
        return "insufficient_data"
    if metrics.mean_brier_difference < 0 and upper < 0:
        return "raw_market_probability_outperformed_expanding_history"
    if metrics.mean_brier_difference > 0 and lower > 0:
        return "historical_frequency_had_lower_error"
    return "difference_not_established"


def _load_snapshot(path: Path | None) -> tuple[ResearchSnapshot | None, str | None]:
    if path is None or not path.is_file():
        return None, "research_snapshot_not_loaded"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ResearchSnapshot.model_validate(payload), None
    except (OSError, json.JSONDecodeError, ValidationError):
        return None, "invalid_research_snapshot"


def create_app(
    *,
    research_metadata_path: Path | None = None,
    ablation_report_path: Path | None = None,
    recorded_summary_path: Path | None = None,
    scenario_dataset_path: Path | None = None,
    service_mode: Literal["demo", "historical"] | None = None,
) -> FastAPI:
    mode = service_mode or os.environ.get("SHOCKGRAPH_SERVICE_MODE", "historical")
    if mode not in ("demo", "historical"):
        raise ValueError("unsupported SHOCKGRAPH_SERVICE_MODE")
    demo = demo_dataset()
    scenario_path = scenario_dataset_path
    if scenario_path is None and os.environ.get("SHOCKGRAPH_SCENARIO_DATASET"):
        scenario_path = Path(os.environ["SHOCKGRAPH_SCENARIO_DATASET"])
    scenario_dataset = None
    scenario_error = "authorized_scenario_dataset_not_loaded"
    if scenario_path is not None:
        try:
            scenario_dataset = ScenarioDataset.model_validate_json(
                scenario_path.read_text(encoding="utf-8")
            )
            if scenario_dataset.source_kind != "licensed_historical":
                raise ValueError("actual input cannot be synthetic")
        except (OSError, ValidationError, ValueError):
            scenario_dataset = None
            scenario_error = "invalid_scenario_dataset"
    configured_path = research_metadata_path
    if configured_path is None and os.environ.get("SHOCKGRAPH_RESEARCH_METADATA"):
        configured_path = Path(os.environ["SHOCKGRAPH_RESEARCH_METADATA"])
    snapshot, snapshot_error = _load_snapshot(configured_path)
    recorded_path = recorded_summary_path
    if recorded_path is None and os.environ.get("SHOCKGRAPH_RECORDED_CPI_SUMMARY"):
        recorded_path = Path(os.environ["SHOCKGRAPH_RECORDED_CPI_SUMMARY"])
    recorded = None
    if recorded_path is not None:
        try:
            recorded = RecordedSummary.model_validate_json(
                recorded_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError):
            snapshot_error = "invalid_recorded_summary"
    ablation_path = ablation_report_path
    if ablation_path is None and os.environ.get("SHOCKGRAPH_ABLATION_REPORT"):
        ablation_path = Path(os.environ["SHOCKGRAPH_ABLATION_REPORT"])
    ablation = None
    ablation_error = "ablation_report_not_loaded"
    if ablation_path is not None:
        try:
            ablation = AblationReport.model_validate_json(ablation_path.read_text(encoding="utf-8"))
        except (OSError, ValidationError):
            ablation_error = "invalid_ablation_report"
    app = FastAPI(
        title="ShockGraph AI API",
        version="0.1.0",
        description="시장 내재확률과 과거 시나리오 반응 분포를 제공하는 읽기 전용 API",
    )
    allowed_origins = [
        origin.strip()
        for origin in os.environ.get(
            "SHOCKGRAPH_WEB_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready", response_model=None)
    def ready() -> dict[str, str] | JSONResponse:
        if mode == "demo":
            return {"status": "ready", "scope": "synthetic_scenario_demo"}
        if scenario_dataset is not None:
            return {
                "status": "ready", "scope": "historical_scenario_analysis",
                "snapshot_checked_at": scenario_dataset.as_of.isoformat(),
            }
        if snapshot is None and recorded is None:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "reason": snapshot_error},
            )
        checked_at = snapshot.source_checked_at if snapshot else None
        if checked_at is None:
            assert recorded is not None
            checked_at = recorded.as_of
        return {
            "status": "ready",
            "scope": "historical_review",
            "snapshot_checked_at": checked_at,
        }

    @app.get("/v1/assets")
    def assets() -> dict[str, Any]:
        return {
            "items": [
                {
                    "asset_id": asset,
                    "currency": "USD",
                    "supported_events": ["CPI"],
                    "supported_horizons": list(HORIZONS),
                    "status": (
                        ablation.diagnostic.status.replace(
                            "insufficient_test_events", "insufficient_data"
                        )
                        if ablation is not None and asset != "GLD"
                        else "insufficient_data"
                    ),
                    "reason": (
                        "historical_frequency_ablation_not_macro_benchmark"
                        if ablation is not None and asset != "GLD"
                        else "asset_price_dataset_not_loaded"
                    ),
                    "role": "supplemental" if asset == "GLD" else "primary",
                }
                for asset in ASSETS
            ]
        }

    @app.get("/v1/research/cpi-probability")
    def cpi_probability() -> dict[str, Any]:
        if snapshot is None and recorded is None:
            raise HTTPException(
                status_code=503,
                detail={"status": "pending", "reason": snapshot_error},
            )
        if snapshot is not None:
            metrics = snapshot.event_probability_comparison
            as_of = snapshot.source_checked_at
            schema = snapshot.schema_version
            provenance = {"kind": "validated_snapshot"}
        else:
            assert recorded is not None
            metrics = recorded.metrics
            as_of = recorded.as_of
            schema = recorded.schema_version
            provenance = {
                "kind": "recorded_aggregate",
                "source_document": recorded.source_document,
                "decimal_places": recorded.decimal_places,
                "recomputed": recorded.recomputed,
            }
        return {
            "status": "ready",
            "scope": "CPI T0.3 contract outcome probability",
            "dataset_snapshot": schema,
            "as_of": as_of,
            "provenance": provenance,
            "independent_event_count": metrics.comparable_events,
            "metrics": metrics.model_dump(),
            "interpretation_boundary": "not_an_asset_return_prediction",
            "finding": _probability_finding(metrics),
        }

    @app.get("/v1/market-expectations/cpi")
    def cpi_market_expectations() -> dict[str, Any]:
        return {
            "status": "pending",
            "reason": "authorized_current_quote_not_connected",
            "event_category": "CPI",
            "contract_definition": "CPI MoM > 0.3%",
            "probability": None,
            "quote_at": None,
            "release_at": None,
        }

    @app.get("/v1/analysis")
    def analysis(
        asset_id: str = Query(min_length=1),
        event_category: str = Query(min_length=1),
        horizon: str = Query(min_length=1),
    ) -> dict[str, Any]:
        normalized_asset = asset_id.upper()
        normalized_event = event_category.upper()
        if normalized_asset not in ASSETS or normalized_event != "CPI" or horizon not in HORIZONS:
            raise HTTPException(
                status_code=404,
                detail={
                    "status": "unsupported",
                    "asset_id": normalized_asset,
                    "event_category": normalized_event,
                    "horizon": horizon,
                },
            )
        if ablation is not None and normalized_asset in ("SPY", "TLT"):
            group = f"{normalized_asset}:{horizon}"
            metric = ablation.diagnostic.comparison.get(group)
            return {
                "status": "exploratory" if metric else "insufficient_data",
                "reason": "historical_frequency_ablation_not_macro_benchmark",
                "asset_id": normalized_asset,
                "event_category": normalized_event,
                "horizon": horizon,
                "independent_event_count": ablation.common_events,
                "diagnostic_min_train": ablation.diagnostic.min_train,
                "diagnostic_test_events": ablation.diagnostic.test_events,
                "research_min_train": ablation.research.min_train,
                "research_test_events": ablation.research.test_events,
                "research_required_test_events": ablation.research.required_test_events,
                "research_status": ablation.research.status,
                "comparison": metric.model_dump() if metric else None,
            }
        return {
            "status": "insufficient_data",
            "reason": "asset_price_dataset_not_loaded",
            "asset_id": normalized_asset,
            "event_category": normalized_event,
            "horizon": horizon,
            "independent_event_count": 0,
        }

    @app.get("/v1/research/cpi-kalshi-ablation")
    def cpi_kalshi_ablation() -> dict[str, Any]:
        if ablation is None:
            raise HTTPException(status_code=503, detail={"reason": ablation_error})
        return ablation.model_dump(mode="json")

    @app.get("/v1/scenarios/cpi")
    def cpi_scenarios(
        asset_id: Literal["SPY", "TLT"] = "SPY",
        horizon: Literal["m5", "m30"] = "m30",
        source: Literal["demo", "actual"] = "actual",
    ) -> dict[str, Any]:
        dataset = demo if source == "demo" else scenario_dataset
        if dataset is None:
            return {
                "status": "pending", "reason": scenario_error,
                "asset_id": asset_id, "horizon": horizon, "scenarios": [],
                "interpretation": "historical_distribution_not_forecast",
            }
        return scenario_report(dataset, asset_id=asset_id, horizon=horizon)

    @app.get("/v1/portfolios/cpi")
    def cpi_portfolio(
        spy_weight: float = Query(default=0.6, ge=0, le=1),
        tlt_weight: float = Query(default=0.4, ge=0, le=1),
        horizon: Literal["m5", "m30"] = "m30",
        source: Literal["demo", "actual"] = "actual",
        portfolio_value: float | None = Query(default=None, ge=0, le=1e12),
    ) -> dict[str, Any]:
        try:
            weights = PortfolioWeights(spy=spy_weight, tlt=tlt_weight)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422, detail="weights must be finite and sum to one"
            ) from exc
        dataset = demo if source == "demo" else scenario_dataset
        if dataset is None:
            return {
                "schema_version": "cpi-portfolio-report-v1", "status": "pending",
                "reason": scenario_error, "horizon": horizon,
                "weights": {"SPY": weights.spy, "TLT": weights.tlt},
                "result": None, "assets": [], "scenarios": [],
            }
        return portfolio_report(dataset, weights=weights, horizon=horizon,
                                portfolio_value=portfolio_value)

    return app


app = create_app()

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

ASSETS = ("SPY", "TLT", "GLD")
HORIZONS = ("m5", "m30")


class ProbabilityMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    eligible_events: int = Field(ge=0)
    comparable_events: int = Field(ge=0)
    raw_market_brier: float = Field(ge=0, le=1)
    expanding_historical_brier: float = Field(ge=0, le=1)
    mean_brier_difference: float
    paired_event_bootstrap95: tuple[float, float]


class ResearchSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    schema_version: Literal["paper-event-v1"]
    series_ticker: Literal["KXCPI"]
    event_count: int = Field(ge=0)
    source_checked_at: str
    event_probability_comparison: ProbabilityMetrics


def _load_snapshot(path: Path | None) -> tuple[ResearchSnapshot | None, str | None]:
    if path is None or not path.is_file():
        return None, "research_snapshot_not_loaded"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ResearchSnapshot.model_validate(payload), None
    except (OSError, json.JSONDecodeError, ValidationError):
        return None, "invalid_research_snapshot"


def create_app(*, research_metadata_path: Path | None = None) -> FastAPI:
    configured_path = research_metadata_path
    if configured_path is None and os.environ.get("SHOCKGRAPH_RESEARCH_METADATA"):
        configured_path = Path(os.environ["SHOCKGRAPH_RESEARCH_METADATA"])
    snapshot, snapshot_error = _load_snapshot(configured_path)
    app = FastAPI(
        title="ShockGraph AI API",
        version="0.1.0",
        description="검증된 연구 스냅샷을 제공하는 읽기 전용 API",
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
        if snapshot is None:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "reason": snapshot_error},
            )
        return {"status": "ready", "snapshot_checked_at": snapshot.source_checked_at}

    @app.get("/v1/assets")
    def assets() -> dict[str, Any]:
        return {
            "items": [
                {
                    "asset_id": asset,
                    "currency": "USD",
                    "supported_events": ["CPI"],
                    "supported_horizons": list(HORIZONS),
                    "status": "insufficient_data",
                    "reason": "asset_price_dataset_not_loaded",
                }
                for asset in ASSETS
            ]
        }

    @app.get("/v1/research/cpi-probability")
    def cpi_probability() -> dict[str, Any]:
        if snapshot is None:
            raise HTTPException(
                status_code=503,
                detail={"status": "pending", "reason": snapshot_error},
            )
        metrics = snapshot.event_probability_comparison
        return {
            "status": "ready",
            "scope": "CPI T0.3 contract outcome probability",
            "dataset_snapshot": snapshot.schema_version,
            "as_of": snapshot.source_checked_at,
            "independent_event_count": metrics.comparable_events,
            "metrics": metrics.model_dump(),
            "interpretation_boundary": "not_an_asset_return_prediction",
            "finding": "raw_market_probability_outperformed_expanding_history",
        }

    @app.get("/v1/analysis")
    def analysis(
        asset_id: str = Query(min_length=1),
        event_category: str = Query(min_length=1),
        horizon: str = Query(min_length=1),
    ) -> dict[str, Any]:
        normalized_asset = asset_id.upper()
        normalized_event = event_category.upper()
        if (
            normalized_asset not in ASSETS
            or normalized_event != "CPI"
            or horizon not in HORIZONS
        ):
            raise HTTPException(
                status_code=404,
                detail={
                    "status": "unsupported",
                    "asset_id": normalized_asset,
                    "event_category": normalized_event,
                    "horizon": horizon,
                },
            )
        return {
            "status": "insufficient_data",
            "reason": "asset_price_dataset_not_loaded",
            "asset_id": normalized_asset,
            "event_category": normalized_event,
            "horizon": horizon,
            "independent_event_count": 0,
        }

    return app


app = create_app()

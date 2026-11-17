"""Read already-reviewed artifacts, without SEC or model calls on the request path."""

from __future__ import annotations

import hmac
import os
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException, Query, Response
from shockgraph_briefing.pipeline import (
    CaptureStatus,
    ReviewedBriefing,
    Symbol,
    Window,
    read_artifact,
    utc_now,
)


def create_app(
    root: Path | None = None,
    *,
    token: str | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> FastAPI:
    directory = (
        root if root is not None else Path(os.environ.get("BRIEFING_DIR", "artifacts/briefing"))
    )
    secret = token if token is not None else os.environ.get("BRIEFING_INTERNAL_TOKEN", "")
    if not secret.isascii() or len(secret) < 32:
        raise ValueError("Set BRIEFING_INTERNAL_TOKEN to a random ASCII value (32+ characters)")
    expected_auth = f"Bearer {secret}".encode()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/api/v1/briefings/{symbol}")
    def get_briefing(
        symbol: Symbol,
        response: Response,
        window: Annotated[Literal["7d"], Query()] = "7d",
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        if not authorization or not hmac.compare_digest(authorization.encode(), expected_auth):
            raise HTTPException(status_code=401, detail="Internal authorization required")
        response.headers["Cache-Control"] = "no-store"
        if symbol != "CAMT":
            return {"symbol": symbol, "status": "insufficient_sources"}
        now = clock()
        try:
            try:
                item = ReviewedBriefing.model_validate_json(
                    read_artifact(directory / "reviewed-camt.json")
                )
            except FileNotFoundError:
                item = None
            if item:
                if item.reviewed_at > now:
                    raise ValueError("Review timestamp cannot be in the future")
                if item.published_at >= now - timedelta(days=30):
                    return item.public_payload(as_of=now)
            try:
                capture = CaptureStatus.model_validate_json(
                    read_artifact(directory / "capture-camt.json")
                )
            except FileNotFoundError:
                return {"symbol": symbol, "status": "pending"}
            if (
                capture.status == "failed"
                or not now - timedelta(days=1) <= capture.checked_at <= now
            ):
                return {"symbol": symbol, "status": "failed"}
        except (OSError, ValueError):
            return {"symbol": symbol, "status": "failed"}
        if capture.filing and capture.filing.accepted_at >= now - Window:
            return {"symbol": symbol, "status": "pending"}
        return {"symbol": symbol, "status": "insufficient_sources"}

    return app

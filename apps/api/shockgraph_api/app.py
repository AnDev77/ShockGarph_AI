"""Authenticated interest assets; official releases remain read-only."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from shockgraph_domain.event_feed import WatchedAsset, build_event_feed

from shockgraph_api.watchlist import PostgresWatchlistStore, WatchlistStore

SUPPORTED_SYMBOLS = frozenset({"QQQ", "SPY"})


class AssetRequest(BaseModel):
    symbol: str


def create_app(store: WatchlistStore, *, jwt_secret: str) -> FastAPI:
    if len(jwt_secret.encode("utf-8")) < 32:
        raise ValueError("JWT verification secret must be at least 32 bytes")
    app = FastAPI(title="ShockGraph interest events", version="0.1.0")
    bearer = HTTPBearer(auto_error=False)
    bearer_dependency = Depends(bearer)

    def current_member(
        credentials: HTTPAuthorizationCredentials | None = bearer_dependency,
    ) -> int:
        if credentials is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token required")
        try:
            claims = jwt.decode(
                credentials.credentials, jwt_secret, algorithms=["HS256"],
                options={"require": ["sub", "exp", "iat"]},
            )
            subject = claims["sub"]
            if not isinstance(subject, str) or not subject.isascii() or not subject.isdecimal():
                raise ValueError("invalid member subject")
            member_id = int(subject)
            if member_id <= 0:
                raise ValueError("invalid member subject")
            return member_id
        except (jwt.PyJWTError, ValueError) as error:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid access token") from error

    def validated_asset(symbol: str) -> WatchedAsset:
        try:
            asset = WatchedAsset(symbol)
        except ValueError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
        if asset.symbol not in SUPPORTED_SYMBOLS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unsupported asset")
        return asset

    @app.get("/health/live")
    def health() -> dict[str, str]:
        return {"status": "process_running"}

    @app.get("/v1/me/watchlist")
    def list_watchlist(member_id: int = Depends(current_member)) -> dict[str, list[str]]:
        return {"symbols": [asset.symbol for asset in store.list_assets(member_id)]}

    @app.post("/v1/me/watchlist")
    def add_watchlist(
        request: AssetRequest, member_id: int = Depends(current_member)
    ) -> dict[str, list[str]]:
        store.add_asset(member_id, validated_asset(request.symbol))
        return {"symbols": [asset.symbol for asset in store.list_assets(member_id)]}

    @app.delete("/v1/me/watchlist/{symbol}")
    def remove_watchlist(
        symbol: str, member_id: int = Depends(current_member)
    ) -> dict[str, list[str]]:
        store.remove_asset(member_id, validated_asset(symbol))
        return {"symbols": [asset.symbol for asset in store.list_assets(member_id)]}

    @app.get("/v1/me/events")
    def list_event_cards(member_id: int = Depends(current_member)) -> dict[str, object]:
        cards = build_event_feed(
            store.list_assets(member_id), store.list_events(member_id), as_of=datetime.now(UTC)
        )
        return {
            "events": [
                {
                    "source": card.source, "event_id": card.event_id,
                    "title": card.title, "scheduled_at": card.scheduled_at.isoformat(),
                    "matched_symbols": card.matched_symbols, "source_url": card.source_url,
                    "status": card.status,
                    "released_at": card.released_at.isoformat() if card.released_at else None,
                    "available_at": card.available_at.isoformat() if card.available_at else None,
                    "release_url": card.release_url,
                }
                for card in cards
            ]
        }

    return app


def create_app_from_env() -> FastAPI:
    """For uvicorn --factory; refuse to boot without authentication and DB config."""
    secret = os.environ.get("SHOCKGRAPH_JWT_SECRET", "")
    dsn = os.environ.get("SHOCKGRAPH_POSTGRES_DSN", "")
    return create_app(PostgresWatchlistStore(dsn), jwt_secret=secret)

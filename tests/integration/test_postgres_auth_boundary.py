"""Exercise the real PostgreSQL schema and doChallenge JWT wire format in CI."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import LiteralString, cast

import psycopg
import pytest
from fastapi.testclient import TestClient
from shockgraph_api.app import create_app
from shockgraph_api.watchlist import PostgresWatchlistStore

SECRET = "a-long-test-secret-with-at-least-thirty-two-bytes"
MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "infra/postgres/migrations/0003_watchlist_events.sql"
)


def _java_style_token(member_id: int, *, secret: str = SECRET, expires_in: int = 3600) -> str:
    """Match doChallenge JwtTokenProvider's UTF-8 HS256 header and payload serialization."""
    issued_at = int(datetime.now(UTC).timestamp())
    header = '{"alg":"HS256","typ":"JWT"}'
    payload = (
        f'{{"sub":"{member_id}","email":"example@example.invalid","role":"USER",'
        f'"iat":{issued_at},"exp":{issued_at + expires_in}}}'
    )

    def encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    content = f"{encode(header.encode())}.{encode(payload.encode())}"
    signature = encode(hmac.new(secret.encode(), content.encode(), hashlib.sha256).digest())
    return f"{content}.{signature}"


def test_java_token_shape_is_decoded_without_using_the_encoder_under_test() -> None:
    """The byte layout comes from doChallenge JwtTokenProvider, not PyJWT's encoder."""
    token = _java_style_token(7)
    encoded_header, encoded_payload, _ = token.split(".")
    assert json.loads(base64.urlsafe_b64decode(encoded_header + "=="))["alg"] == "HS256"
    assert json.loads(base64.urlsafe_b64decode(encoded_payload + "=="))["sub"] == "7"


def test_real_postgres_migration_and_member_boundaries() -> None:
    dsn = os.getenv("SHOCKGRAPH_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("isolated PostgreSQL test service is not configured")

    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            database_row = cursor.fetchone()
            if database_row is None or not database_row[0].endswith("_test"):
                raise ValueError("Refusing migration and cleanup outside an isolated test database")
        # Reapplying the migration is expected to preserve rows and remain safe.
        # The checked-in migration is trusted code; never use this for external input.
        migration_sql = cast(LiteralString, MIGRATION.read_text(encoding="utf-8"))
        connection.execute(migration_sql)
        connection.execute(migration_sql)
        connection.execute(
            "TRUNCATE official_release_assets, official_release_cards, watchlist_assets"
        )
        scheduled = datetime.now(UTC) + timedelta(days=1)
        connection.execute(
            "INSERT INTO official_release_cards "
            "(source, external_event_id, title, scheduled_at, source_url, "
            "released_at, available_at, release_url) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                "federal-reserve", "isolated-example", "Test announcement", scheduled,
                "https://www.federalreserve.gov/", scheduled,
                scheduled + timedelta(minutes=1), "https://www.federalreserve.gov/",
            ),
        )
        connection.execute(
            "INSERT INTO official_release_assets (source, external_event_id, symbol) "
            "VALUES (%s, %s, %s)",
            ("federal-reserve", "isolated-example", "QQQ"),
        )

    client = TestClient(create_app(PostgresWatchlistStore(dsn), jwt_secret=SECRET))

    def auth(
        member_id: int, *, secret: str = SECRET, expires_in: int = 3600
    ) -> dict[str, str]:
        token = _java_style_token(member_id, secret=secret, expires_in=expires_in)
        return {"Authorization": f"Bearer {token}"}

    assert client.get("/v1/me/watchlist").status_code == 401
    wrong_secret = auth(7, secret="wrong-secret-32-bytes-minimum-value")
    assert client.get("/v1/me/watchlist", headers=wrong_secret).status_code == 401
    assert client.get("/v1/me/watchlist", headers=auth(7, expires_in=-1)).status_code == 401
    for _ in range(2):
        response = client.post("/v1/me/watchlist", json={"symbol": "QQQ"}, headers=auth(7))
        assert response.json() == {"symbols": ["QQQ"]}
    assert client.get("/v1/me/watchlist", headers=auth(8)).json() == {"symbols": []}
    assert client.delete("/v1/me/watchlist/QQQ", headers=auth(8)).json() == {"symbols": []}
    assert client.get("/v1/me/watchlist", headers=auth(7)).json() == {"symbols": ["QQQ"]}
    cards = client.get("/v1/me/events", headers=auth(7)).json()["events"]
    assert len(cards) == 1
    assert cards[0]["matched_symbols"] == ["QQQ"]
    assert cards[0]["release_url"] is None
    assert client.get("/v1/me/events", headers=auth(8)).json() == {"events": []}

    with psycopg.connect(dsn) as connection:
        connection.execute(
            "TRUNCATE official_release_assets, official_release_cards, watchlist_assets"
        )

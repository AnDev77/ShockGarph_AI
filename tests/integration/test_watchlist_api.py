from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient
from shockgraph_api.app import create_app
from shockgraph_domain.event_feed import OfficialEvent, WatchedAsset

SECRET = "a-long-test-secret-with-at-least-thirty-two-bytes"


class MemoryStore:
    def __init__(self) -> None:
        self.assets: dict[int, set[str]] = {}
        self.events: tuple[OfficialEvent, ...] = ()

    def list_assets(self, member_id: int) -> tuple[WatchedAsset, ...]:
        return tuple(WatchedAsset(s) for s in sorted(self.assets.get(member_id, set())))

    def add_asset(self, member_id: int, asset: WatchedAsset) -> None:
        self.assets.setdefault(member_id, set()).add(asset.symbol)

    def remove_asset(self, member_id: int, asset: WatchedAsset) -> None:
        self.assets.setdefault(member_id, set()).discard(asset.symbol)

    def list_events(self, member_id: int) -> tuple[OfficialEvent, ...]:
        watched = self.assets.get(member_id, set())
        return tuple(e for e in self.events if watched.intersection(e.related_symbols))


def _token(member_id: str, *, secret: str = SECRET, expiry: int = 3600) -> dict[str, str]:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": member_id, "email": "test@example.invalid", "role": "USER",
            "iat": now, "exp": now + timedelta(seconds=expiry),
        },
        secret, algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def test_watchlist_requires_verified_member_and_is_member_scoped() -> None:
    store = MemoryStore()
    client = TestClient(create_app(store, jwt_secret=SECRET))

    assert client.get("/v1/me/watchlist").status_code == 401
    wrong_signature = _token("1", secret="bad-secret-of-at-least-thirty-two-characters")
    assert client.post(
        "/v1/me/watchlist", json={"symbol": "QQQ"}, headers=wrong_signature
    ).status_code == 401
    assert client.get("/v1/me/watchlist", headers=_token("1", expiry=-1)).status_code == 401
    add_first = client.post("/v1/me/watchlist", json={"symbol": " qqq "}, headers=_token("1"))
    add_again = client.post("/v1/me/watchlist", json={"symbol": "QQQ"}, headers=_token("1"))
    assert add_first.json() == add_again.json() == {"symbols": ["QQQ"]}
    assert client.get("/v1/me/watchlist", headers=_token("2")).json() == {"symbols": []}
    assert client.delete("/v1/me/watchlist/QQQ", headers=_token("2")).json() == {"symbols": []}
    assert client.get("/v1/me/watchlist", headers=_token("1")).json() == {"symbols": ["QQQ"]}


def test_event_cards_do_not_leak_another_members_interest_or_future_release() -> None:
    store = MemoryStore()
    client = TestClient(create_app(store, jwt_secret=SECRET))
    now = datetime.now(UTC)
    store.events = (
        OfficialEvent(
            source="federal-reserve", event_id="example-fomc", title="FOMC example",
            scheduled_at=now + timedelta(days=1),
            source_url="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            related_symbols=("QQQ",),
            released_at=now + timedelta(days=1),
            available_at=now + timedelta(days=1, minutes=1),
            release_url="https://www.federalreserve.gov/newsevents/pressreleases/",
        ),
    )
    client.post("/v1/me/watchlist", json={"symbol": "QQQ"}, headers=_token("1"))
    client.post("/v1/me/watchlist", json={"symbol": "SPY"}, headers=_token("2"))

    first = client.get("/v1/me/events", headers=_token("1")).json()["events"]
    second = client.get("/v1/me/events", headers=_token("2")).json()["events"]
    assert len(first) == 1 and second == []
    assert first[0]["status"] == "scheduled"
    assert first[0]["matched_symbols"] == ["QQQ"]
    assert first[0]["released_at"] is first[0]["release_url"] is None


def test_rejects_unsupported_symbol_and_untrusted_subject() -> None:
    store = MemoryStore()
    client = TestClient(create_app(store, jwt_secret=SECRET))

    unsupported = client.post("/v1/me/watchlist", json={"symbol": "NVDA"}, headers=_token("1"))
    assert unsupported.status_code == 422
    assert client.get("/v1/me/events", headers=_token("not-a-member")).status_code == 401
    assert store.assets == {}

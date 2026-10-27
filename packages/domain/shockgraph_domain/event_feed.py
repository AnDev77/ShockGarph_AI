"""Interest-asset event cards built only from explicit, time-valid source records."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("event timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _symbol(value: str) -> str:
    symbol = value.strip().upper()
    valid = all(c.isascii() and (c.isalnum() or c in ".-") for c in symbol)
    if not symbol or len(symbol) > 20 or not valid:
        raise ValueError("invalid asset symbol")
    return symbol


@dataclass(frozen=True)
class WatchedAsset:
    symbol: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _symbol(self.symbol))


@dataclass(frozen=True)
class OfficialEvent:
    source: str
    event_id: str
    title: str
    scheduled_at: datetime
    source_url: str
    related_symbols: tuple[str, ...]
    released_at: datetime | None = None
    available_at: datetime | None = None
    release_url: str | None = None

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.event_id.strip() or not self.title.strip():
            raise ValueError("event source, id and title are required")
        if not self.source_url.startswith("https://"):
            raise ValueError("official source URL must use HTTPS")
        object.__setattr__(self, "scheduled_at", _utc(self.scheduled_at))
        object.__setattr__(
            self, "related_symbols", tuple(dict.fromkeys(_symbol(s) for s in self.related_symbols))
        )
        if not self.related_symbols:
            raise ValueError("event requires an explicit asset relationship")
        if (self.released_at is None) != (self.available_at is None):
            raise ValueError("release and availability timestamps must be supplied together")
        if self.released_at is not None and self.available_at is not None:
            object.__setattr__(self, "released_at", _utc(self.released_at))
            object.__setattr__(self, "available_at", _utc(self.available_at))
            if self.available_at < self.released_at:
                raise ValueError("release cannot be available before publication")
            if self.release_url is None or not self.release_url.startswith("https://"):
                raise ValueError("published event requires an official HTTPS release URL")
        elif self.release_url is not None:
            raise ValueError("unpublished event cannot have a release URL")


@dataclass(frozen=True)
class EventCard:
    source: str
    event_id: str
    title: str
    scheduled_at: datetime
    matched_symbols: tuple[str, ...]
    source_url: str
    status: str
    released_at: datetime | None
    available_at: datetime | None
    release_url: str | None


def build_event_feed(
    watched: Iterable[WatchedAsset], events: Iterable[OfficialEvent], *, as_of: datetime
) -> tuple[EventCard, ...]:
    """Expose a publication only when its source was usable at the query time."""
    query_time = _utc(as_of)
    symbols = {asset.symbol for asset in watched}
    if not symbols:
        return ()
    cards: list[EventCard] = []
    seen: set[tuple[str, str]] = set()
    for event in events:
        matched = tuple(s for s in event.related_symbols if s in symbols)
        if not matched:
            continue
        key = (event.source, event.event_id)
        if key in seen:
            raise ValueError("duplicate official event identity")
        seen.add(key)
        published = event.available_at is not None and event.available_at <= query_time
        cards.append(
            EventCard(
                source=event.source,
                event_id=event.event_id,
                title=event.title,
                scheduled_at=event.scheduled_at,
                matched_symbols=matched,
                source_url=event.source_url,
                status="published" if published else "scheduled",
                released_at=event.released_at if published else None,
                available_at=event.available_at if published else None,
                release_url=event.release_url if published else None,
            )
        )
    return tuple(sorted(cards, key=lambda c: (c.scheduled_at, c.source, c.event_id)))

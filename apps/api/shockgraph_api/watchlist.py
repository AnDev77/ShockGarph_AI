"""PostgreSQL interest assets and read-only official event links."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import psycopg
from shockgraph_domain.event_feed import OfficialEvent, WatchedAsset


class WatchlistStore(Protocol):
    def list_assets(self, member_id: int) -> tuple[WatchedAsset, ...]: ...

    def add_asset(self, member_id: int, asset: WatchedAsset) -> None: ...

    def remove_asset(self, member_id: int, asset: WatchedAsset) -> None: ...

    def list_events(self, member_id: int) -> tuple[OfficialEvent, ...]: ...


class PostgresWatchlistStore:
    def __init__(self, dsn: str, connect: Callable[..., psycopg.Connection] = psycopg.connect):
        if not dsn:
            raise ValueError("a PostgreSQL DSN is required")
        self._dsn = dsn
        self._connect = connect

    def list_assets(self, member_id: int) -> tuple[WatchedAsset, ...]:
        with self._connect(self._dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT symbol FROM watchlist_assets WHERE member_id = %s ORDER BY symbol",
                (member_id,),
            )
            return tuple(WatchedAsset(row[0]) for row in cursor.fetchall())

    def add_asset(self, member_id: int, asset: WatchedAsset) -> None:
        with self._connect(self._dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO watchlist_assets (member_id, symbol) VALUES (%s, %s) "
                "ON CONFLICT (member_id, symbol) DO NOTHING",
                (member_id, asset.symbol),
            )

    def remove_asset(self, member_id: int, asset: WatchedAsset) -> None:
        with self._connect(self._dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM watchlist_assets WHERE member_id = %s AND symbol = %s",
                (member_id, asset.symbol),
            )

    def list_events(self, member_id: int) -> tuple[OfficialEvent, ...]:
        with self._connect(self._dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT e.source, e.external_event_id, e.title, e.scheduled_at, "
                "e.source_url, e.released_at, e.available_at, e.release_url, "
                "ARRAY_AGG(a.symbol ORDER BY a.symbol) "
                "FROM official_release_cards e "
                "JOIN official_release_assets a "
                "ON (a.source, a.external_event_id) = (e.source, e.external_event_id) "
                "JOIN watchlist_assets w ON w.symbol = a.symbol AND w.member_id = %s "
                "GROUP BY e.source, e.external_event_id "
                "ORDER BY e.scheduled_at, e.source, e.external_event_id",
                (member_id,),
            )
            return tuple(
                OfficialEvent(
                    source=row[0], event_id=row[1], title=row[2], scheduled_at=row[3],
                    source_url=row[4], released_at=row[5], available_at=row[6],
                    release_url=row[7], related_symbols=tuple(row[8]),
                )
                for row in cursor.fetchall()
            )

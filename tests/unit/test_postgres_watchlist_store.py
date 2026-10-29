from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from shockgraph_api.watchlist import PostgresWatchlistStore
from shockgraph_domain.event_feed import WatchedAsset


def _store(rows: list[tuple[object, ...]]) -> tuple[PostgresWatchlistStore, MagicMock]:
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchall.return_value = rows
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value = cursor
    connector = MagicMock(return_value=connection)
    return PostgresWatchlistStore("postgresql://not-connected", connect=connector), cursor


def test_database_commands_scope_user_identity_as_bound_parameter() -> None:
    store, cursor = _store([("QQQ",)])
    assert store.list_assets(7) == (WatchedAsset("QQQ"),)
    sql, values = cursor.execute.call_args.args
    assert "WHERE member_id = %s" in sql
    assert values == (7,)

    store.add_asset(7, WatchedAsset("SPY"))
    sql, values = cursor.execute.call_args.args
    assert "ON CONFLICT (member_id, symbol) DO NOTHING" in sql
    assert values == (7, "SPY")

    store.remove_asset(7, WatchedAsset("SPY"))
    sql, values = cursor.execute.call_args.args
    assert "WHERE member_id = %s AND symbol = %s" in sql
    assert values == (7, "SPY")


def test_event_query_joins_only_the_authenticated_members_assets() -> None:
    scheduled = datetime(2026, 10, 28, 18, tzinfo=UTC)
    row = (
        "fed", "example", "FOMC", scheduled, "https://www.federalreserve.gov/",
        None, None, None, ["QQQ"],
    )
    store, cursor = _store([row])
    result = store.list_events(7)

    assert result[0].related_symbols == ("QQQ",)
    sql, values = cursor.execute.call_args.args
    assert "JOIN watchlist_assets w ON w.symbol = a.symbol AND w.member_id = %s" in sql
    assert values == (7,)

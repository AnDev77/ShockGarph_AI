from __future__ import annotations

from pathlib import Path

SQL = (Path(__file__).parents[2] / "infra/postgres/migrations/0003_watchlist_events.sql").read_text(
    encoding="utf-8"
).upper()


def test_watchlist_and_official_release_have_separate_keys_and_utc_times() -> None:
    assert "PRIMARY KEY (MEMBER_ID, SYMBOL)" in SQL
    assert "PRIMARY KEY (SOURCE, EXTERNAL_EVENT_ID)" in SQL
    assert "REFERENCES OFFICIAL_RELEASE_CARDS" in SQL
    assert SQL.count("TIMESTAMPTZ") >= 4
    assert "TIMESTAMP WITHOUT TIME ZONE" not in SQL

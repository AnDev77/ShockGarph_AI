from __future__ import annotations

from pathlib import Path

MIGRATION = (
    Path(__file__).parents[2] / "infra" / "postgres" / "migrations" / "0001_ingestion.sql"
)


def test_ingestion_migration_has_required_tables_and_utc_types() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").upper()

    for table in ("RAW_PAYLOADS", "EVENTS", "MARKET_SNAPSHOTS", "ORDERBOOK_SNAPSHOTS"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "TIMESTAMP WITHOUT TIME ZONE" not in sql
    assert sql.count("TIMESTAMPTZ") >= 10


def test_ingestion_migration_enforces_source_identity_and_payload_lineage() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").upper()

    assert "UNIQUE (SOURCE, EXTERNAL_EVENT_ID)" in sql
    assert "RAW_PAYLOAD_HASH CHAR(64)" in sql
    assert "REFERENCES RAW_PAYLOADS(PAYLOAD_HASH)" in sql


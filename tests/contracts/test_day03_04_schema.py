from __future__ import annotations

from pathlib import Path

MIGRATION = (
    Path(__file__).parents[2] / "infra" / "postgres" / "migrations" / "0002_day03_04.sql"
)


def test_day03_04_migration_has_data_outbox_and_registry_tables() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").upper()

    for table in (
        "ASSETS",
        "ASSET_PRICES",
        "FEATURE_SNAPSHOTS",
        "NORMALIZATION_RUNS",
        "INGESTION_OUTBOX",
        "MODEL_VERSIONS",
        "MODEL_METRICS",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "CREATE EXTENSION IF NOT EXISTS TIMESCALEDB" in sql
    assert sql.count("CREATE_HYPERTABLE") == 2


def test_schema_tracks_idempotency_lineage_and_uncertainty() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").upper()

    assert "UNIQUE (PAYLOAD_HASH, TRANSFORMATION_VERSION, TARGET_TABLE)" in sql
    assert "ARTIFACT_CHECKSUM CHAR(64)" in sql
    assert "DATASET_CHECKSUM CHAR(64)" in sql
    assert "SAMPLE_SIZE INTEGER" in sql
    assert "CONFIDENCE_LOWER DOUBLE PRECISION" in sql
    assert "CONFIDENCE_UPPER DOUBLE PRECISION" in sql

BEGIN;

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS assets (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    venue TEXT NOT NULL,
    currency CHAR(3) NOT NULL,
    asset_type TEXT NOT NULL CHECK (asset_type IN ('equity', 'etf', 'bond', 'fx', 'commodity')),
    UNIQUE (symbol, venue)
);

CREATE TABLE IF NOT EXISTS asset_prices (
    asset_id BIGINT NOT NULL REFERENCES assets(id),
    source TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    session_date DATE NOT NULL,
    close NUMERIC(24, 8) NOT NULL CHECK (close > 0),
    adjusted_close NUMERIC(24, 8) CHECK (adjusted_close > 0),
    volume NUMERIC(28, 8) CHECK (volume >= 0),
    raw_payload_hash CHAR(64) NOT NULL REFERENCES raw_payloads(payload_hash),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (asset_id, observed_at, source),
    CHECK (raw_payload_hash ~ '^[0-9a-f]{64}$')
);

SELECT create_hypertable(
    'asset_prices',
    by_range('observed_at'),
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS asset_prices_session_idx
    ON asset_prices (asset_id, session_date DESC, observed_at DESC);

CREATE TABLE IF NOT EXISTS feature_snapshots (
    event_id BIGINT NOT NULL REFERENCES events(id),
    feature_name TEXT NOT NULL,
    feature_as_of TIMESTAMPTZ NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    value NUMERIC NOT NULL,
    transformation_version TEXT NOT NULL,
    raw_payload_hash CHAR(64) NOT NULL REFERENCES raw_payloads(payload_hash),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (event_id, feature_name, feature_as_of, transformation_version),
    CHECK (feature_as_of <= observed_at),
    CHECK (raw_payload_hash ~ '^[0-9a-f]{64}$')
);

SELECT create_hypertable(
    'feature_snapshots',
    by_range('feature_as_of'),
    if_not_exists => TRUE,
    migrate_data => TRUE
);

CREATE TABLE IF NOT EXISTS normalization_runs (
    idempotency_key CHAR(64) PRIMARY KEY,
    payload_hash CHAR(64) NOT NULL REFERENCES raw_payloads(payload_hash),
    transformation_version TEXT NOT NULL,
    target_table TEXT NOT NULL,
    record_count INTEGER NOT NULL CHECK (record_count >= 0),
    processed_at TIMESTAMPTZ NOT NULL,
    UNIQUE (payload_hash, transformation_version, target_table)
);

CREATE TABLE IF NOT EXISTS ingestion_outbox (
    id UUID PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error TEXT,
    CHECK (published_at IS NULL OR published_at >= created_at)
);

CREATE INDEX IF NOT EXISTS ingestion_outbox_unpublished_idx
    ON ingestion_outbox (created_at) WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS model_versions (
    id BIGSERIAL PRIMARY KEY,
    model_name TEXT NOT NULL,
    version TEXT NOT NULL,
    model_type TEXT NOT NULL CHECK (model_type IN ('identity_baseline', 'calibration')),
    artifact_uri TEXT NOT NULL CHECK (artifact_uri LIKE 's3://%'),
    artifact_checksum CHAR(64) NOT NULL,
    dataset_checksum CHAR(64) NOT NULL,
    trained_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('candidate', 'approved', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (model_name, version),
    CHECK (artifact_checksum ~ '^[0-9a-f]{64}$'),
    CHECK (dataset_checksum ~ '^[0-9a-f]{64}$')
);

CREATE TABLE IF NOT EXISTS model_metrics (
    model_version_id BIGINT NOT NULL REFERENCES model_versions(id) ON DELETE CASCADE,
    split TEXT NOT NULL CHECK (split IN ('train', 'validation', 'test')),
    metric_name TEXT NOT NULL,
    metric_value DOUBLE PRECISION NOT NULL CHECK (metric_value >= 0),
    sample_size INTEGER NOT NULL CHECK (sample_size > 0),
    confidence_lower DOUBLE PRECISION NOT NULL CHECK (confidence_lower BETWEEN 0 AND 1),
    confidence_upper DOUBLE PRECISION NOT NULL CHECK (confidence_upper BETWEEN 0 AND 1),
    PRIMARY KEY (model_version_id, split, metric_name),
    CHECK (confidence_lower <= confidence_upper)
);

COMMIT;

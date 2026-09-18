BEGIN;

CREATE TABLE IF NOT EXISTS raw_payloads (
    payload_hash CHAR(64) PRIMARY KEY,
    source TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    request_params_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    observed_at TIMESTAMPTZ NOT NULL,
    storage_path TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (payload_hash ~ '^[0-9a-f]{64}$')
);

CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    external_event_id TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    open_time TIMESTAMPTZ NOT NULL,
    close_time TIMESTAMPTZ NOT NULL,
    resolved_time TIMESTAMPTZ,
    result TEXT CHECK (result IN ('yes', 'no')),
    status TEXT NOT NULL CHECK (status IN ('unopened', 'open', 'closed', 'settled')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    raw_payload_hash CHAR(64) NOT NULL REFERENCES raw_payloads(payload_hash),
    UNIQUE (source, external_event_id),
    CHECK (close_time >= open_time),
    CHECK (resolved_time IS NULL OR resolved_time >= open_time)
);

CREATE TABLE IF NOT EXISTS market_snapshots (
    id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES events(id),
    market_ticker TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    yes_bid NUMERIC(8, 6) CHECK (yes_bid BETWEEN 0 AND 1),
    yes_ask NUMERIC(8, 6) CHECK (yes_ask BETWEEN 0 AND 1),
    no_bid NUMERIC(8, 6) CHECK (no_bid BETWEEN 0 AND 1),
    no_ask NUMERIC(8, 6) CHECK (no_ask BETWEEN 0 AND 1),
    last_price NUMERIC(8, 6) CHECK (last_price BETWEEN 0 AND 1),
    volume NUMERIC(24, 6) NOT NULL CHECK (volume >= 0),
    open_interest NUMERIC(24, 6) NOT NULL CHECK (open_interest >= 0),
    raw_payload_hash CHAR(64) NOT NULL REFERENCES raw_payloads(payload_hash),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (yes_bid IS NULL OR yes_ask IS NULL OR yes_bid <= yes_ask),
    CHECK (no_bid IS NULL OR no_ask IS NULL OR no_bid <= no_ask),
    UNIQUE (event_id, market_ticker, observed_at, raw_payload_hash)
);

CREATE INDEX IF NOT EXISTS market_snapshots_event_time_idx
    ON market_snapshots (event_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS orderbook_snapshots (
    id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES events(id),
    market_ticker TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('yes', 'no')),
    price NUMERIC(8, 6) NOT NULL CHECK (price BETWEEN 0 AND 1),
    quantity NUMERIC(24, 6) NOT NULL CHECK (quantity >= 0),
    level INTEGER NOT NULL CHECK (level >= 0),
    raw_payload_hash CHAR(64) NOT NULL REFERENCES raw_payloads(payload_hash),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (market_ticker, observed_at, side, price, level)
);

CREATE INDEX IF NOT EXISTS orderbook_snapshots_market_time_idx
    ON orderbook_snapshots (market_ticker, observed_at DESC);

COMMIT;


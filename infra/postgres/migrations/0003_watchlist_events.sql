BEGIN;

-- Member IDs come from the verified doChallenge token. No account credentials are stored here.
CREATE TABLE IF NOT EXISTS watchlist_assets (
    member_id BIGINT NOT NULL CHECK (member_id > 0),
    symbol TEXT NOT NULL CHECK (symbol ~ '^[A-Z0-9.-]{1,20}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (member_id, symbol)
);

-- Official releases are separate from Kalshi prediction-market events.
CREATE TABLE IF NOT EXISTS official_release_cards (
    source TEXT NOT NULL,
    external_event_id TEXT NOT NULL,
    title TEXT NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    source_url TEXT NOT NULL,
    released_at TIMESTAMPTZ,
    available_at TIMESTAMPTZ,
    release_url TEXT,
    PRIMARY KEY (source, external_event_id),
    CHECK ((released_at IS NULL) = (available_at IS NULL)),
    CHECK (available_at IS NULL OR available_at >= released_at),
    CHECK ((release_url IS NULL) = (released_at IS NULL))
);

CREATE TABLE IF NOT EXISTS official_release_assets (
    source TEXT NOT NULL,
    external_event_id TEXT NOT NULL,
    symbol TEXT NOT NULL CHECK (symbol ~ '^[A-Z0-9.-]{1,20}$'),
    PRIMARY KEY (source, external_event_id, symbol),
    FOREIGN KEY (source, external_event_id)
        REFERENCES official_release_cards (source, external_event_id)
);

CREATE INDEX IF NOT EXISTS official_release_assets_symbol_idx
    ON official_release_assets (symbol, source, external_event_id);

COMMIT;

BEGIN;

-- Private, canonical research rows. Only the earliest audited index per origin
-- and first complete label per horizon may be inserted by the application.
CREATE TABLE IF NOT EXISTS official_forward_risk_scores (
    origin_session DATE NOT NULL,
    symbol TEXT NOT NULL CHECK (symbol IN ('TLT', 'SPY')),
    horizon SMALLINT NOT NULL CHECK (horizon IN (5, 20)),
    model_name TEXT NOT NULL CHECK (model_name IN ('trailing', 'ewma', 'garch', 'gjr')),
    model_version TEXT NOT NULL,
    prediction_at TIMESTAMPTZ NOT NULL,
    label_end_at TIMESTAMPTZ NOT NULL,
    label_captured_at TIMESTAMPTZ NOT NULL,
    forecast_index_sha256 CHAR(64) NOT NULL CHECK (forecast_index_sha256 ~ '^[0-9a-f]{64}$'),
    label_index_sha256 CHAR(64) NOT NULL CHECK (label_index_sha256 ~ '^[0-9a-f]{64}$'),
    score_artifact_sha256 CHAR(64) NOT NULL CHECK (score_artifact_sha256 ~ '^[0-9a-f]{64}$'),
    score_artifact_uri TEXT NOT NULL CHECK (score_artifact_uri LIKE 's3://%'),
    realized_volatility DOUBLE PRECISION NOT NULL,
    absolute_error DOUBLE PRECISION NOT NULL,
    public_performance_allowed BOOLEAN NOT NULL DEFAULT FALSE
        CHECK (public_performance_allowed = FALSE),
    PRIMARY KEY (origin_session, symbol, horizon, model_name),
    CHECK (prediction_at < label_end_at AND label_end_at <= label_captured_at),
    CHECK (realized_volatility >= 0 AND realized_volatility < 'Infinity'::DOUBLE PRECISION),
    CHECK (absolute_error >= 0 AND absolute_error < 'Infinity'::DOUBLE PRECISION)
);

CREATE INDEX IF NOT EXISTS official_forward_risk_scores_horizon_idx
    ON official_forward_risk_scores (symbol, horizon, origin_session DESC);

COMMIT;

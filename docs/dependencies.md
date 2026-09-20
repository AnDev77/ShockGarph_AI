# Dependency Decisions

## Runtime

### Pydantic

Added on Day 2 to enforce UTC timestamps, bounded probabilities, non-negative
quantities, strict event status/result values, and cross-field quote validation.
These contracts sit at the ingestion boundary before database writes.

### HTTPX

Added on Day 2 for a timeout-aware, testable, read-only HTTP collector. The
collector exposes GET requests only, accepts only approved Kalshi public/demo base
URLs and public path prefixes, and uses `MockTransport` in tests. It contains no
authentication, account, order, or execution support.

## Development

- `pytest`: deterministic unit, contract, and integration tests.
- `ruff`: linting and import formatting.
- `pyright`: static type-checking contract; the Codex sandbox may block its Node
  bootstrap even when configuration is valid.

## Planned infrastructure

These are approved architecture targets, not installed runtime dependencies yet.
Each item must pass its stated gate before it is added to Docker Compose or the
Python dependency lock.

### PostgreSQL with TimescaleDB

Use one PostgreSQL-compatible operational boundary for relational metadata and
time-series observations. Add hypertables only for price, probability, feature,
and prediction series after the Day 3 schema tests pass.

### S3-compatible object storage

Keep the current local immutable store behind a protocol. Add MinIO for local
integration after object-key, checksum, collision, and retry tests exist. Model
binaries and dataset snapshots belong here; their metadata belongs in PostgreSQL.

### RabbitMQ

Use RabbitMQ for asynchronous ingestion work only after raw-first persistence and
a PostgreSQL outbox are implemented. Consumers must use idempotency keys and
tolerate at-least-once delivery. Kafka remains outside the MVP.

### Prefect

Use Prefect to schedule and observe collection, dataset build, training, and
evaluation flows. Domain and transformation functions must remain callable and
testable without a running Prefect server.

### Redis

Add Redis only after FastAPI latency or database-load measurements justify it.
Use cache-aside with TTLs for validated responses; never store the only copy of a
feature, prediction, or model result in Redis.

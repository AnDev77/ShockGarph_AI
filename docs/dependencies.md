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


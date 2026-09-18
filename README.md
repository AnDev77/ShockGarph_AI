# ShockGraph AI

ShockGraph AI is an event-driven portfolio risk research MVP. It calibrates
prediction-market probabilities, estimates lagged asset responses, and explains
how scenario risk reaches a user's portfolio. It does not trade or provide
personalized buy/sell recommendations.

## Current milestone

Days 1-2 are implemented:

- repository boundaries for API, web, collector, analytics packages, and infra;
- immutable Kalshi API contract fixtures;
- contract normalization and payload hashing;
- event-level split and timestamp leakage guards;
- a read-only public API feasibility probe;
- documented GO / REDUCE_SCOPE / BLOCKED decisions.
- strict UTC event, market-snapshot, and order-book records;
- PostgreSQL ingestion migration with payload lineage constraints;
- a GET-only public collector with bounded retry and cursor pagination;
- content-addressed immutable raw payload storage.

No UI or trained model is included yet by design.

The current delivery review is in `docs/reviews/day-01-02-review.md`.

## Run locally

Python 3.12 is required.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```

On macOS or Linux, use `.venv/bin/python` instead.

## Repository map

- `apps/api`: FastAPI boundary, scheduled for Week 2.
- `apps/web`: Next.js boundary, scheduled for Week 3.
- `apps/collector`: read-only ingestion boundary.
- `packages/domain`: core financial and portfolio contracts.
- `packages/data_pipeline`: source contracts, lineage, and leakage guards.
- `packages/*`: later calibration, event-study, graph, and risk engines.
- `docs/data-feasibility.md`: Day 1 data gate and scope decision.
- `data/fixtures`: small, source-shaped payloads used in deterministic tests.
- `docs/reviews`: per-request code structure and user inspection checklists.

## Safety boundary

Only public read endpoints or demo environments may be used. Secrets, account
data, order placement, and execution code are outside the MVP.

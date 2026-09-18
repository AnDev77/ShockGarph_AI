# Data Feasibility Gate

Status date: 2026-09-17 UTC/KST

## Executive decision

Overall Day 1 decision: **REDUCE_SCOPE**.

The public API surface is technically sufficient for event metadata, current and
historical markets, public trades, current order books, and market candlesticks.
It is not sufficient for historical order-book reconstruction. More importantly,
the current Kalshi Developer Agreement blocks storing or sharing API data for a
public research product without prior written authorization. Technical access is
therefore not the same as permission to ship.

| Dataset or use | Decision | Reason |
|---|---|---|
| Event and series discovery | GO_TECHNICAL | Public unauthenticated GET responses verified. |
| Current markets and public trades | GO_TECHNICAL | Responses and cursor pagination verified. |
| Historical markets and trades | GO_TECHNICAL | Historical partition and responses verified. |
| Historical probability candles | GO_TECHNICAL | Daily candle response verified on a settled CPI market. |
| Current order book | GO_TECHNICAL | Public depth response verified without credentials. |
| Historical order book | BLOCKED | No historical order-book endpoint is documented. |
| Calibration baseline | GO | Resolved outcomes and probability candles are obtainable. |
| Logistic calibration | REDUCE_SCOPE | Only about 107 resolved events across the selected core series before splitting. |
| LightGBM calibration | BLOCKED_FOR_MVP | Far below the 300 independent-event gate. |
| Oil event family | REDUCE_SCOPE | The richer weekly series is small and stale; current inventory series is very short. |
| Public redistribution or hosted product | BLOCKED_LEGAL | Written permission or a separately licensed source is required. |
| US/Korean asset prices | NOT_VERIFIED | A licensed asset-price source is a separate Gate B task. |

## Sources checked

- API environments: https://docs.kalshi.com/getting_started/api_environments
- Public market data: https://docs.kalshi.com/getting_started/quick_start_market_data
- Historical partition: https://docs.kalshi.com/getting_started/historical_data
- Rate limits: https://docs.kalshi.com/getting_started/rate_limits
- Events: https://docs.kalshi.com/api-reference/events/get-events
- Markets: https://docs.kalshi.com/api-reference/market/get-markets
- Trades: https://docs.kalshi.com/api-reference/market/get-trades
- Candlesticks: https://docs.kalshi.com/api-reference/market/get-market-candlesticks
- Developer Agreement v1.1: https://kalshi-public-docs.s3.amazonaws.com/Kalshi-Developer-Agreement.pdf

## Verified environments

Production REST base URL:

`https://external-api.kalshi.com/trade-api/v2`

Demo REST base URL:

`https://external-api.demo.kalshi.co/trade-api/v2`

Production and demo credentials are separate. A one-market public GET returned
successfully from the demo environment. This does not remove the data-use terms.

## Endpoint coverage

| Need | Endpoint | Actual result | Key fields |
|---|---|---|---|
| Events | `GET /events` | 200, cursor present | event ticker, series, title, category, times |
| Markets | `GET /markets` | 200, cursor present | bid/ask, last price, volume, OI, result |
| Trades | `GET /markets/trades` | 200, cursor present | ticker, price, count, trade timestamp |
| Historical cutoff | `GET /historical/cutoff` | 200 | cutoff timestamps by entity |
| Historical markets | `GET /historical/markets` | 200, cursor present | settled result and settlement time |
| Historical trades | `GET /historical/trades` | 200, cursor present | older public trades |
| Historical candles | `GET /historical/markets/{ticker}/candlesticks` | 200 | 1m/1h/1d probability OHLC, volume, OI |
| Current order book | `GET /markets/{ticker}/orderbook` | 200 | current YES/NO bid levels |
| Historical order book | none found | unavailable | no reconstructable depth history |

The observed historical cutoff was `2026-07-19T00:00:00Z`. Kalshi documents a
target live-data window of roughly three months; callers must query both live and
historical partitions and de-duplicate at the market/trade identifier boundary.

## Independent sample counts

Counts below are from the read-only probe on 2026-09-17. `resolved_event_count`
is the modeling unit; multiple snapshots or strike markets do not increase it.

| Event family | Series | Events | Resolved events | Markets | Resolved markets | Settlement range |
|---|---|---:|---:|---:|---:|---|
| FOMC decision | KXFEDDECISION | 39 | 29 | 200 | 145 | 2023-05-03 to 2026-09-16 |
| US CPI | KXCPI | 66 | 63 | 533 | 508 | 2021-07-15 to 2026-09-11 |
| Oil monthly | KXOIL | 10 | 9 | 28 | 28 | 2022-03-10 to 2022-08-18 |
| Oil weekly alternative | KXOILW | 15 | 15 | 30 | 30 | 2022-03-10 to 2022-08-25 |
| EIA crude inventory alternative | KXEIACRUDEW | 4 | 3 | 52 | 39 | 2026-09-02 to 2026-09-16 |

The selected FOMC, CPI, and weekly-oil series provide at most 107 independent
resolved events before chronological train/validation/test splitting. That is
enough for a pooled logistic comparison under the specification's 100-event
threshold, but not enough for a credible LightGBM claim. Per-category test sets
will be especially small and must show confidence intervals.

## Fields and gaps

Available for calibration:

- market bid/ask and last price;
- volume and open interest;
- market/event/series identifiers;
- trade timestamps, prices, and quantities;
- resolution result and settlement timestamp;
- 1-minute, 1-hour, and 1-day probability candles.

Unavailable or incomplete:

- no historical order-book snapshots;
- retrieval time is not a source field and must be stamped by the collector;
- the event object is metadata; binary outcomes live on market records;
- spread and imbalance history must be collected prospectively or omitted;
- event-family mapping requires a reviewed series allowlist;
- raw API category labels are not a stable macro taxonomy;
- the API contract may change without prior notice.

## Rate limits and collection behavior

The documented Basic event-contract tier has a read budget of 200 tokens per
second. Limits use token buckets, and a 429 response currently has no
`Retry-After` or `X-RateLimit-*` header. Collectors must use bounded exponential
backoff, cursor checkpoints, idempotent upserts, and immutable payload hashes.

## Licensing and public deployment gate

Kalshi Developer Agreement v1.1 states that API use is limited to facilitating a
member's own trading, and prohibits collecting, caching, aggregating, storing, or
sharing API content for other purposes without prior written authorization.

Consequences for this MVP:

1. Do not ship raw Kalshi payloads, prices, charts, or a hosted collector publicly.
2. Use repository fixtures only for deterministic development and demos.
3. Obtain written Kalshi authorization or replace the source with a licensed data
   provider before public deployment or a commercial pilot.
4. Treat even derived public metrics as requiring legal/source review; do not
   assume aggregation alone cures the restriction.

This is a product gate, not legal advice.

## Gate B: asset data

US ETF, USD/KRW, and Korean ETF sources have not been approved in this milestone.
The next data task must document history depth, corporate-action handling,
timezone/calendar alignment, redistribution rights, and whether only derived
statistics may be exposed. Until then, asset ingestion is `NOT_VERIFIED`.

## Go-forward scope

- Keep FOMC and CPI as the two required real-data analytical verticals.
- Keep oil behind a feature flag until a larger or separately licensed event set
  is identified; use KXOILW only for exploratory tests.
- Build market-probability baseline and pooled logistic calibration first.
- Do not build LightGBM until the independent resolved-event count exceeds 300.
- Do not depend on historical order-book imbalance in the MVP feature set.
- Keep public demos on synthetic/sanitized fixtures until data rights are cleared.

## Reproduce the technical probe

```bash
python scripts/probe_kalshi.py
```

The probe performs only unauthenticated GET requests and prints a summary. It
does not place orders, access accounts, or write source payloads to disk.


# ShockGraph AI Project Specification

The canonical source for this repository is the user-provided
`shockgraph-ai-project-spec.md`. The implementation contract is:

- three-week MVP with FOMC, US CPI, and an oil event family;
- probability calibration, event study, lagged transmission graph, and portfolio
  risk engine;
- Brier score as the primary calibration metric;
- chronological event-grouped splits with strict future-data leakage guards;
- UTC storage, source hashes, sample sizes, confidence intervals, and limitations;
- no trading, order placement, personalized recommendations, Kafka, Kubernetes,
  GNN, LSTM, Transformer price prediction, authentication, or payments;
- Week 3 Next.js interface only after the analytical vertical slice is validated;
- public deployment only after source licensing is cleared.

The full staged plan and detailed formulas are reflected in `docs/`, `configs/`,
package boundaries, and `AGENTS.md`.


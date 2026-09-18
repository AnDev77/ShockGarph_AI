# Collector boundary

Collectors must be read-only, idempotent, UTC-normalized, and preserve immutable
raw payloads with SHA-256 hashes.

`shockgraph_collector.client.KalshiPublicClient` currently provides:

- approved production/demo base URLs only;
- public GET paths only;
- bounded retry for 429 and transient 5xx responses;
- cursor pagination with repeated-cursor protection;
- direct persistence into the immutable raw store.

# Data Lineage

`raw -> clean -> feature -> artifact`

Each record must retain source, UTC ingestion time, immutable payload SHA-256,
schema version, and transformation version. Raw payloads are never mutated.
Public artifacts must respect the source license and may expose only approved
fields or derived statistics.

Day 2 raw object layout:

`{root}/{source}/{yyyy}/{mm}/{dd}/{endpoint}/{request_hash}/{observed_at}_{payload_hash}.json`

The retrieval timestamp is part of the identity so unchanged probability
snapshots observed at different times remain distinct. Re-running the same
request with the same timestamp and payload is idempotent.


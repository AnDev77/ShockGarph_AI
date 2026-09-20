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

Target object-store lineage keeps the same logical identity when local storage is
replaced by MinIO or S3:

`s3://{bucket}/raw/{source}/{yyyy}/{mm}/{dd}/{endpoint}/{request_hash}/{observed_at}_{payload_hash}.json`

The collector writes the immutable object before it records metadata and an
outbox job in PostgreSQL. Normalization messages may be redelivered, so the clean
write identity is `payload_hash + transformation_version + target_table`. Model
artifacts use the same rule: PostgreSQL stores version, metrics, URI, and checksum;
the binary remains in object storage.

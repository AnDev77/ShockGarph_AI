"""Verify selected private R2 scores before storing their PostgreSQL metadata."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages/risk_engine"),
                str(ROOT / "packages/data_pipeline")]

from scripts.archive_forward_capture import _encoded  # noqa: E402
from scripts.persist_score_metadata import save_official_score_rows  # noqa: E402
from scripts.private_r2 import configured_r2  # noqa: E402
from scripts.score_archived_forward import (  # noqa: E402
    official_score_plan,
    persist_private_scores,
    score_archived_pair,
)


def persist_official_metadata(s3: Any, connection: Any, *, bucket: str,
                              prefix: str) -> dict[str, object]:
    """Commit each selected two-asset horizon only after immutable readback.

    Requires migration 0003. A conflicting row aborts the active transaction;
    previously committed horizons can be retried safely.
    """
    plan = official_score_plan(s3, bucket=bucket, prefix=prefix)
    inserted = 0
    for forecast_key, label_key, horizon in plan:
        result = persist_private_scores(s3, bucket=bucket, forecast_index_key=forecast_key,
                                        label_index_key=label_key, horizon=horizon)
        key = result["score_key"]
        source = s3.get_object(Bucket=bucket, Key=forecast_key)["Body"].read()
        label = s3.get_object(Bucket=bucket, Key=label_key)["Body"].read()
        scores = tuple(item for item in score_archived_pair(
            s3, bucket=bucket, forecast_index_key=forecast_key,
            label_index_key=label_key) if item.horizon == horizon)
        expected = _encoded({
            "schema_version": 1, "status": "private_forward_scores",
            "forecast_index_key": forecast_key,
            "forecast_index_sha256": hashlib.sha256(source).hexdigest(),
            "label_index_key": label_key,
            "label_index_sha256": hashlib.sha256(label).hexdigest(),
            "public_performance_allowed": False,
            "scores": [asdict(item) for item in scores],
        })
        head = s3.head_object(Bucket=bucket, Key=key)
        actual = s3.get_object(Bucket=bucket, Key=key)["Body"].read(len(expected) + 1)
        digest = hashlib.sha256(expected).hexdigest()
        if (actual != expected or head.get("ContentLength") != len(expected)
                or head.get("Metadata", {}).get("sha256") != digest):
            raise ValueError("score artifact readback differs")
        with connection.transaction():
            inserted += save_official_score_rows(
                connection.cursor(), scores,
                forecast_index_sha256=hashlib.sha256(source).hexdigest(),
                label_index_sha256=hashlib.sha256(label).hexdigest(),
                score_artifact_sha256=digest, score_artifact_uri=f"s3://{bucket}/{key}")
    return {"status": "private_official_metadata_verified", "score_count": len(plan) * 2,
            "new_row_count": inserted, "public_performance_allowed": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="공식 점수 원본 재감사와 비공개 DB 저장")
    parser.add_argument("--prefix", default="shockgraph-research")
    args = parser.parse_args(argv)
    try:
        dsn = os.environ["SHOCKGRAPH_POSTGRES_DSN"]
        client, bucket = configured_r2()
        psycopg = importlib.import_module("psycopg")
        with psycopg.connect(dsn, autocommit=True) as connection:
            report = persist_official_metadata(client, connection, bucket=bucket,
                                               prefix=args.prefix)
    except Exception:
        print(json.dumps({"status": "private_official_metadata_failed"}))
        return 2
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

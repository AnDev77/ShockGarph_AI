"""Score a private forecast using a separately audited later price vintage."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import sys
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages/data_pipeline"),
                str(ROOT / "packages/risk_engine")]

from shockgraph_risk.exploratory_history import HistoryPrice  # noqa: E402
from shockgraph_risk.forward_risk_capture import (  # noqa: E402
    ForwardHorizon,
    ForwardRiskRecord,
    ForwardRiskScore,
    score_forward_risk_record,
)

from scripts.archive_forward_capture import _encoded, _write_once, audit_capture  # noqa: E402
from scripts.private_r2 import bucket_budget_guard  # noqa: E402

_COLUMNS = ["session_date", "observed_at", "available_at", "close", "adjusted_close",
            "volume"]


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("capture needs a UTC timestamp")
    return parsed.astimezone(UTC)


def _record(payload: dict[str, Any]) -> ForwardRiskRecord:
    targets = tuple(ForwardHorizon(
        horizon=item["horizon"],
        first_outcome_session=date.fromisoformat(item["first_outcome_session"]),
        last_outcome_session=date.fromisoformat(item["last_outcome_session"]),
        label_end_at=_utc(item["label_end_at"]),
        trailing_volatility=item["trailing_volatility"],
        ewma_volatility=item["ewma_volatility"],
        garch_volatility=item["garch_volatility"],
        gjr_volatility=item["gjr_volatility"],
    ) for item in payload["horizons"])
    return ForwardRiskRecord(
        symbol=payload["symbol"], origin_session=date.fromisoformat(payload["origin_session"]),
        source_snapshot_sha256=payload["source_snapshot_sha256"],
        source_captured_at=_utc(payload["source_captured_at"]),
        prediction_at=_utc(payload["prediction_at"]), horizons=targets,
    )


def score_archived_pair(s3: Any, *, bucket: str, forecast_index_key: str,
                        label_index_key: str) -> tuple[ForwardRiskScore, ...]:
    """Require two independently read-verified archive indexes before scoring."""
    if forecast_index_key == label_index_key:
        raise ValueError("label needs a separate archive index")
    audit_capture(s3, bucket=bucket, index_key=forecast_index_key)
    audit_capture(s3, bucket=bucket, index_key=label_index_key)
    forecast = json.loads(s3.get_object(Bucket=bucket, Key=forecast_index_key)["Body"].read())
    label = json.loads(s3.get_object(Bucket=bucket, Key=label_index_key)["Body"].read())
    if forecast["status"] != "forward_forecasts_archived":
        raise ValueError("source index has no forward forecasts")
    prefix = label_index_key.split("/records/", 1)[0]
    manifest_bytes = s3.get_object(Bucket=bucket, Key=prefix + "/manifest.json")["Body"].read()
    manifest = json.loads(manifest_bytes)
    sources = {item["key"]: item["sha256"] for item in label["source_objects"]}
    results = []
    for payload in forecast["forecasts"]:
        record = _record(payload)
        entry = next(item for item in manifest["prices"] if item["symbol"] == record.symbol)
        key = prefix + f"/{record.symbol}/prices.csv"
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        digest = hashlib.sha256(body).hexdigest()
        if digest != sources.get(key) or digest != entry["normalized_csv_sha256"]:
            raise ValueError("later price vintage hash differs")
        captured = _utc(entry["capture"])
        reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig"), newline=""), strict=True)
        if reader.fieldnames != _COLUMNS:
            raise ValueError("later price columns differ")
        prices = []
        for row in reader:
            if None in row or any(value is None or not value for value in row.values()):
                raise ValueError("later price row is incomplete")
            if _utc(row["available_at"]) != captured:
                raise ValueError("later price availability differs from capture")
            value = float(row["adjusted_close"])
            if not math.isfinite(value) or value <= 0:
                raise ValueError("later adjusted price is invalid")
            prices.append(HistoryPrice(date.fromisoformat(row["session_date"]), value))
        if len(prices) != entry["session_count"]:
            raise ValueError("later price session count differs")
        results.extend(score_forward_risk_record(record, prices,
                       label_snapshot_sha256=digest, label_captured_at=captured))
    if not results:
        raise ValueError("no mature forward label exists")
    return tuple(results)


def persist_private_scores(s3: Any, *, bucket: str, forecast_index_key: str,
                           label_index_key: str) -> dict[str, Any]:
    """Persist a verified score for one source/label pair without public values."""
    scores = score_archived_pair(s3, bucket=bucket,
                                 forecast_index_key=forecast_index_key,
                                 label_index_key=label_index_key)
    source_bytes = s3.get_object(Bucket=bucket, Key=forecast_index_key)["Body"].read()
    label_bytes = s3.get_object(Bucket=bucket, Key=label_index_key)["Body"].read()
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    label_sha = hashlib.sha256(label_bytes).hexdigest()
    prefix = forecast_index_key.split("/captures/", 1)[0]
    if prefix == forecast_index_key:
        raise ValueError("score needs a private capture prefix")
    key = f"{prefix}/scores/{source_sha}/{label_sha}.json"
    payload = _encoded({
        "schema_version": 1, "status": "private_forward_scores",
        "forecast_index_key": forecast_index_key, "forecast_index_sha256": source_sha,
        "label_index_key": label_index_key, "label_index_sha256": label_sha,
        "public_performance_allowed": False,
        "scores": [asdict(item) for item in scores],
    })
    bucket_budget_guard(s3, bucket)(len(payload))
    created = _write_once(s3, bucket, key, payload)
    return {"status": "private_scores_readback_verified", "created": created,
            "score_count": len(scores), "score_key": key,
            "public_performance_allowed": False}

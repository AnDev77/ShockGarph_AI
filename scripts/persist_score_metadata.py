"""Transaction-scoped PostgreSQL adapter for private official risk score metadata."""

from __future__ import annotations

import math
import re
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages/risk_engine")]

from shockgraph_risk.forward_risk_capture import ForwardRiskScore  # noqa: E402

_SHA = re.compile(r"^[0-9a-f]{64}$")
_MODELS = (("trailing", "trailing_absolute_error"),
           ("ewma", "ewma_absolute_error"),
           ("garch", "garch_absolute_error"),
           ("gjr", "gjr_absolute_error"))
_INSERT = """
INSERT INTO official_forward_risk_scores (
    origin_session, symbol, horizon, model_name, model_version,
    prediction_at, label_end_at, label_captured_at,
    forecast_index_sha256, label_index_sha256, score_artifact_sha256,
    score_artifact_uri, realized_volatility, absolute_error, public_performance_allowed
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (origin_session, symbol, horizon, model_name) DO NOTHING
RETURNING 1
"""
_SELECT = """
SELECT origin_session, symbol, horizon, model_name, model_version,
       prediction_at, label_end_at, label_captured_at,
       forecast_index_sha256, label_index_sha256, score_artifact_sha256,
       score_artifact_uri, realized_volatility, absolute_error, public_performance_allowed
FROM official_forward_risk_scores
WHERE origin_session = %s AND symbol = %s AND horizon = %s AND model_name = %s
"""


class Cursor(Protocol):
    def execute(self, query: str, params: tuple[object, ...]) -> Any: ...
    def fetchone(self) -> tuple[object, ...] | None: ...


def save_official_score_rows(
    cursor: Cursor, scores: tuple[ForwardRiskScore, ...], *,
    forecast_index_sha256: str, label_index_sha256: str,
    score_artifact_sha256: str, score_artifact_uri: str,
) -> int:
    """Insert two assets' four baseline errors atomically in caller's transaction.

    The caller must audit both index bytes, apply official_score_plan, verify the
    archived score artifact, then commit only after this function returns.
    """
    if len(scores) != 2 or {score.symbol for score in scores} != {"TLT", "SPY"}:
        raise ValueError("official metadata needs two assets")
    if any(not _SHA.fullmatch(value) for value in (
        forecast_index_sha256, label_index_sha256, score_artifact_sha256
    )):
        raise ValueError("official metadata checksum is invalid")
    if not score_artifact_uri.startswith("s3://") or len(score_artifact_uri) <= 5:
        raise ValueError("official metadata requires a private artifact URI")
    reference = scores[0]
    for score in scores:
        if (score.origin_session != reference.origin_session
                or score.horizon != reference.horizon
                or score.prediction_at != reference.prediction_at
                or score.label_end_at != reference.label_end_at
                or score.label_captured_at != reference.label_captured_at
                or score.horizon not in (5, 20)
                or score.public_performance_allowed
                or score.prediction_at.utcoffset() != timedelta(0)
                or score.label_end_at.utcoffset() != timedelta(0)
                or score.label_captured_at.utcoffset() != timedelta(0)
                or not score.prediction_at < score.label_end_at <= score.label_captured_at
                or not _SHA.fullmatch(score.source_snapshot_sha256)
                or not _SHA.fullmatch(score.label_snapshot_sha256)):
            raise ValueError("official metadata provenance is invalid")
        values = (score.realized_volatility, *(getattr(score, field) for _, field in _MODELS))
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("official metadata value is invalid")

    rows = tuple((score.origin_session, score.symbol, score.horizon, model,
                  "price_baselines_v1", score.prediction_at, score.label_end_at,
                  score.label_captured_at, forecast_index_sha256, label_index_sha256,
                  score_artifact_sha256, score_artifact_uri, score.realized_volatility,
                  getattr(score, error_field), False)
                 for score in scores for model, error_field in _MODELS)
    created = 0
    for row in rows:
        cursor.execute(_INSERT, row)
        if cursor.fetchone() is not None:
            created += 1
            continue
        cursor.execute(_SELECT, row[:4])
        existing = cursor.fetchone()
        if existing is None or tuple(existing) != row:
            raise ValueError("official metadata conflict; roll back the transaction")
    return created

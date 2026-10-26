from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from shockgraph_risk.forward_risk_capture import ForwardRiskScore

from scripts.persist_score_metadata import save_official_score_rows


class MemoryCursor:
    def __init__(self) -> None:
        self.rows: dict[tuple[object, ...], tuple[object, ...]] = {}
        self.result: tuple[object, ...] | None = None

    def execute(self, query: str, params: tuple[object, ...]) -> MemoryCursor:
        key = params[:4]
        if "INSERT INTO official_forward_risk_scores" in query:
            if key in self.rows:
                self.result = None
            else:
                self.rows[key] = params
                self.result = (1,)
        elif "SELECT origin_session" in query:
            self.result = self.rows.get(key)
        else:
            raise AssertionError("unexpected metadata query")
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return self.result


def _scores() -> tuple[ForwardRiskScore, ForwardRiskScore]:
    label_end = datetime(2026, 10, 30, 20, tzinfo=UTC)
    return tuple(ForwardRiskScore(
        symbol=symbol, origin_session=date(2026, 10, 23), horizon=5,
        prediction_at=label_end - timedelta(days=7), label_end_at=label_end,
        label_captured_at=label_end + timedelta(days=3),
        source_snapshot_sha256="a" * 64, label_snapshot_sha256="b" * 64,
        realized_volatility=0.012, trailing_absolute_error=0.001,
        ewma_absolute_error=0.002, garch_absolute_error=0.003,
        gjr_absolute_error=0.004,
    ) for symbol in ("TLT", "SPY"))  # type: ignore[return-value]


def test_metadata_rows_are_idempotent_and_conflicts_fail_closed() -> None:
    cursor = MemoryCursor()
    args = dict(forecast_index_sha256="c" * 64, label_index_sha256="d" * 64,
                score_artifact_sha256="e" * 64,
                score_artifact_uri="s3://private-risk-research/research/scores/result.json")
    scores = _scores()
    assert save_official_score_rows(cursor, scores, **args) == 8
    assert save_official_score_rows(cursor, scores, **args) == 0
    assert len(cursor.rows) == 8
    with pytest.raises(ValueError, match="conflict"):
        save_official_score_rows(cursor, scores, **{**args, "label_index_sha256": "f" * 64})
    assert len(cursor.rows) == 8


def test_metadata_rejects_incomplete_pair_and_invalid_private_values() -> None:
    cursor = MemoryCursor()
    args = dict(forecast_index_sha256="c" * 64, label_index_sha256="d" * 64,
                score_artifact_sha256="e" * 64,
                score_artifact_uri="s3://private-risk-research/research/scores/result.json")
    with pytest.raises(ValueError, match="two assets"):
        save_official_score_rows(cursor, _scores()[:1], **args)
    with pytest.raises(ValueError, match="checksum"):
        save_official_score_rows(cursor, _scores(), **{**args, "score_artifact_sha256": "bad"})
    first, second = _scores()
    with pytest.raises(ValueError, match="value"):
        corrupted = replace(second, garch_absolute_error=float("nan"))
        save_official_score_rows(cursor, (first, corrupted), **args)
    assert not cursor.rows

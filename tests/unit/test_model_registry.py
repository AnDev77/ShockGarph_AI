from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from shockgraph_domain.model_registry import ModelMetric, ModelVersion


def test_model_version_requires_traceable_object_artifact() -> None:
    version = ModelVersion(
        model_name="kalshi-identity",
        version="2026.09.22.1",
        model_type="identity_baseline",
        artifact_uri="s3://shockgraph-models/calibration/identity.json",
        artifact_checksum="a" * 64,
        dataset_checksum="b" * 64,
        trained_at=datetime(2026, 9, 22, tzinfo=UTC),
        metrics=(
            ModelMetric(
                name="brier_score",
                value=0.2,
                sample_size=20,
                confidence_lower=0.1,
                confidence_upper=0.3,
            ),
        ),
    )

    assert version.metrics[0].sample_size == 20


def test_model_version_rejects_local_artifact_path() -> None:
    with pytest.raises(ValidationError, match="artifact_uri"):
        ModelVersion(
            model_name="kalshi-identity",
            version="v1",
            model_type="identity_baseline",
            artifact_uri="artifacts/model.json",
            artifact_checksum="a" * 64,
            dataset_checksum="b" * 64,
            trained_at=datetime(2026, 9, 22, tzinfo=UTC),
            metrics=(
                ModelMetric(
                    name="brier_score",
                    value=0.2,
                    sample_size=20,
                    confidence_lower=0.1,
                    confidence_upper=0.3,
                ),
            ),
        )

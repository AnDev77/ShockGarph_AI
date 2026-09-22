from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shockgraph_domain.records import PayloadHash, _as_utc


class ModelMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    value: float = Field(ge=0)
    sample_size: int = Field(gt=0)
    confidence_lower: float = Field(ge=0, le=1)
    confidence_upper: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_interval(self) -> ModelMetric:
        if self.confidence_lower > self.confidence_upper:
            raise ValueError("confidence_lower cannot exceed confidence_upper")
        return self


class ModelVersion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    model_name: str = Field(min_length=1)
    version: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    model_type: Literal["identity_baseline", "calibration"]
    artifact_uri: str = Field(pattern=r"^s3://[a-z0-9][a-z0-9.-]*/.+$")
    artifact_checksum: PayloadHash
    dataset_checksum: PayloadHash
    trained_at: datetime
    status: Literal["candidate", "approved", "rejected"] = "candidate"
    metrics: tuple[ModelMetric, ...] = Field(min_length=1)

    @field_validator("trained_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)

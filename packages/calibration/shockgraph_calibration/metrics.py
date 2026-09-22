from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from shockgraph_calibration.dataset import CalibrationObservation


@dataclass(frozen=True, slots=True)
class BrierScoreReport:
    score: float
    sample_size: int
    standard_error: float
    confidence_lower: float
    confidence_upper: float


def identity_predictions(rows: Sequence[CalibrationObservation]) -> tuple[float, ...]:
    return tuple(row.probability for row in rows)


def brier_score(
    probabilities: Sequence[float], outcomes: Sequence[int], *, confidence_z: float = 1.96
) -> BrierScoreReport:
    if len(probabilities) != len(outcomes):
        raise ValueError("probabilities and outcomes must have equal length")
    if not probabilities:
        raise ValueError("at least one sample is required")

    losses: list[float] = []
    for probability, outcome in zip(probabilities, outcomes, strict=True):
        if not 0 <= probability <= 1:
            raise ValueError("probabilities must be in [0, 1]")
        if outcome not in (0, 1):
            raise ValueError("outcomes must be binary")
        losses.append((probability - outcome) ** 2)

    sample_size = len(losses)
    score = math.fsum(losses) / sample_size
    if sample_size == 1:
        standard_error = 0.0
    else:
        variance = math.fsum((loss - score) ** 2 for loss in losses) / (sample_size - 1)
        standard_error = math.sqrt(variance / sample_size)
    margin = confidence_z * standard_error
    return BrierScoreReport(
        score=score,
        sample_size=sample_size,
        standard_error=standard_error,
        confidence_lower=max(0.0, score - margin),
        confidence_upper=min(1.0, score + margin),
    )

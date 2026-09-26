"""Conservative probability transforms for explicitly verified event partitions."""

from __future__ import annotations

import math
from typing import TypedDict


class PartitionResult(TypedDict):
    probabilities: dict[str, float]
    raw_sum: float
    normalization_factor: float
    method: str


def binary_book_midpoint(yes_bid: float, no_bid: float) -> dict[str, float]:
    """Infer YES ask from NO bid; fees are not included in the midpoint."""
    if any(not math.isfinite(x) or not 0 <= x <= 1 for x in (yes_bid, no_bid)):
        raise ValueError("bids must be finite and between zero and one")
    spread = 1 - yes_bid - no_bid
    if spread < -1e-9:
        raise ValueError("crossed orderbook")
    if spread < 0:
        spread = 0.0
    yes_midpoint = yes_bid + spread / 2
    return {"yes_midpoint": yes_midpoint, "no_midpoint": 1 - yes_midpoint, "spread": spread}


def normalize_verified_partition(
    raw_midpoints: dict[str, float],
    *,
    partition_verified: bool = False,
    max_deviation: float = 0.05,
) -> PartitionResult:
    """Scale a complete, disjoint outcome set; refuse missing tails and large incoherence."""
    if not partition_verified:
        raise ValueError("exhaustive disjoint partition must be verified against contract rules")
    if len(raw_midpoints) < 2 or not 0 <= max_deviation < 1:
        raise ValueError("at least two outcomes and a valid deviation limit required")
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in raw_midpoints.values()):
        raise ValueError("invalid market midpoint")
    total = math.fsum(raw_midpoints.values())
    if abs(total - 1) > max_deviation:
        raise ValueError("raw probability sum deviation exceeds limit")
    return {
        "probabilities": {name: p / total for name, p in raw_midpoints.items()},
        "raw_sum": total,
        "normalization_factor": 1 / total,
        "method": "verified_partition_midpoint_scale_v1",
    }


def thresholds_to_partition(
    thresholds: list[float], probabilities_above: list[float]
) -> list[float]:
    """Turn an exhaustive chain of strict exceedance contracts into disjoint bins."""
    if not thresholds or len(thresholds) != len(probabilities_above):
        raise ValueError("matched threshold and probability arrays required")
    if any(not math.isfinite(x) for x in thresholds + probabilities_above):
        raise ValueError("all inputs must be finite")
    if any(a >= b for a, b in zip(thresholds, thresholds[1:], strict=False)):
        raise ValueError("thresholds must be strictly increasing")
    if any(not 0 <= p <= 1 for p in probabilities_above) or any(
        a < b for a, b in zip(probabilities_above, probabilities_above[1:], strict=False)
    ):
        raise ValueError("threshold probabilities must be monotone decreasing")
    return [
        1 - probabilities_above[0],
        *(a - b for a, b in zip(probabilities_above, probabilities_above[1:], strict=False)),
        probabilities_above[-1],
    ]

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from shockgraph_analytics.cpi_distribution import (
    ConsensusVintage,
    ThresholdQuote,
    build_threshold_distribution,
    consensus_surprise_probabilities,
)

AS_OF = datetime(2026, 10, 14, 12, 25, tzinfo=UTC)
RELEASE_AT = AS_OF + timedelta(minutes=5)


def quote(threshold: float, probability: float, *, minutes_old: int = 1) -> ThresholdQuote:
    return ThresholdQuote(
        event_id="KXCPI-26SEP",
        market_ticker=f"KXCPI-26SEP-T{threshold}",
        threshold=threshold,
        observed_at=AS_OF - timedelta(minutes=minutes_old),
        available_at=AS_OF - timedelta(minutes=minutes_old),
        probability_above=probability,
        spread=0.04,
        raw_hash="a" * 64,
    )


def test_monotone_thresholds_become_exhaustive_disjoint_bins() -> None:
    distribution = build_threshold_distribution(
        [quote(0.2, 0.8), quote(0.3, 0.5), quote(0.4, 0.2)], as_of=AS_OF
    )

    assert distribution.raw_monotone is True
    assert distribution.thresholds == (0.2, 0.3, 0.4)
    assert distribution.probabilities_above == pytest.approx((0.8, 0.5, 0.2))
    assert distribution.bin_probabilities == pytest.approx((0.2, 0.3, 0.3, 0.2))
    assert sum(distribution.bin_probabilities) == pytest.approx(1)
    assert distribution.method == "unweighted_isotonic_l2_v1"


def test_small_orderbook_inversion_is_projected_but_large_repair_abstains() -> None:
    distribution = build_threshold_distribution(
        [quote(0.2, 0.70), quote(0.3, 0.72), quote(0.4, 0.20)],
        as_of=AS_OF,
        max_isotonic_adjustment=0.05,
    )

    assert distribution.raw_monotone is False
    assert distribution.probabilities_above == pytest.approx((0.71, 0.71, 0.20))
    assert distribution.max_isotonic_adjustment == pytest.approx(0.01)

    with pytest.raises(ValueError, match="isotonic adjustment"):
        build_threshold_distribution(
            [quote(0.2, 0.20), quote(0.3, 0.80)],
            as_of=AS_OF,
            max_isotonic_adjustment=0.05,
        )


def test_curve_rejects_mixed_events_duplicate_thresholds_and_bad_quote_time() -> None:
    other_event = quote(0.3, 0.5).model_copy(update={"event_id": "KXCPI-26AUG"})
    with pytest.raises(ValueError, match="one event"):
        build_threshold_distribution([quote(0.2, 0.7), other_event], as_of=AS_OF)
    with pytest.raises(ValueError, match="duplicate threshold"):
        build_threshold_distribution([quote(0.2, 0.7), quote(0.2, 0.6)], as_of=AS_OF)
    with pytest.raises(ValueError, match="stale"):
        build_threshold_distribution([quote(0.2, 0.7, minutes_old=16)], as_of=AS_OF)
    with pytest.raises(ValueError, match="after as_of"):
        build_threshold_distribution(
            [
                quote(0.2, 0.7).model_copy(
                    update={"available_at": AS_OF + timedelta(seconds=1)}
                )
            ],
            as_of=AS_OF,
        )


def test_consensus_boundaries_produce_below_inline_above_probabilities() -> None:
    distribution = build_threshold_distribution(
        [quote(0.2, 0.80), quote(0.3, 0.55), quote(0.4, 0.20)], as_of=AS_OF
    )
    consensus = ConsensusVintage(
        event_id="KXCPI-26SEP",
        expected_mom=0.3,
        available_at=AS_OF - timedelta(hours=1),
        source="approved_consensus_snapshot",
        raw_hash="b" * 64,
    )

    result = consensus_surprise_probabilities(
        distribution,
        consensus,
        release_at=RELEASE_AT,
        reporting_step=0.1,
    )

    assert result.probability_below == pytest.approx(0.20)
    assert result.probability_inline == pytest.approx(0.25)
    assert result.probability_above == pytest.approx(0.55)
    assert sum(
        (result.probability_below, result.probability_inline, result.probability_above)
    ) == pytest.approx(1)


def test_consensus_conversion_abstains_without_exact_boundaries_or_valid_vintage() -> None:
    missing_boundary = build_threshold_distribution(
        [quote(0.1, 0.9), quote(0.3, 0.55)], as_of=AS_OF
    )
    consensus = ConsensusVintage(
        event_id="KXCPI-26SEP",
        expected_mom=0.3,
        available_at=AS_OF - timedelta(hours=1),
        source="approved_consensus_snapshot",
        raw_hash="b" * 64,
    )
    with pytest.raises(ValueError, match="exact consensus boundaries"):
        consensus_surprise_probabilities(
            missing_boundary,
            consensus,
            release_at=RELEASE_AT,
            reporting_step=0.1,
        )

    late_consensus = consensus.model_copy(update={"available_at": AS_OF + timedelta(seconds=1)})
    complete = build_threshold_distribution(
        [quote(0.2, 0.8), quote(0.3, 0.55)], as_of=AS_OF
    )
    with pytest.raises(ValueError, match="available by as_of"):
        consensus_surprise_probabilities(
            complete,
            late_consensus,
            release_at=RELEASE_AT,
            reporting_step=0.1,
        )


def test_release_and_curve_must_remain_strictly_pre_event() -> None:
    distribution = build_threshold_distribution(
        [quote(0.2, 0.8), quote(0.3, 0.55)], as_of=AS_OF
    )
    consensus = ConsensusVintage(
        event_id="KXCPI-26SEP",
        expected_mom=0.3,
        available_at=AS_OF,
        source="approved_consensus_snapshot",
        raw_hash="b" * 64,
    )
    with pytest.raises(ValueError, match="strictly before release"):
        consensus_surprise_probabilities(
            distribution,
            consensus,
            release_at=AS_OF,
            reporting_step=0.1,
        )

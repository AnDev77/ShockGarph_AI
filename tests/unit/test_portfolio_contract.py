from __future__ import annotations

import pytest
from shockgraph_domain.portfolio import PortfolioValidationError, validate_positions


def test_weights_must_sum_to_one_without_explicit_normalization() -> None:
    positions = [{"symbol": "SPY", "weight": 0.6}, {"symbol": "TLT", "weight": 0.3}]

    with pytest.raises(PortfolioValidationError, match="sum to 1"):
        validate_positions(positions)


def test_explicit_normalization_is_reported() -> None:
    positions = [{"symbol": "SPY", "weight": 60}, {"symbol": "TLT", "weight": 40}]

    result = validate_positions(positions, normalize=True)

    assert result.normalized is True
    assert [position.weight for position in result.positions] == pytest.approx([0.6, 0.4])


def test_duplicate_symbol_is_rejected() -> None:
    positions = [{"symbol": "SPY", "weight": 0.5}, {"symbol": "spy", "weight": 0.5}]

    with pytest.raises(PortfolioValidationError, match="duplicate"):
        validate_positions(positions)


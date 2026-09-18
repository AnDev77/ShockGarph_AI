from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class PortfolioValidationError(ValueError):
    """Raised when portfolio positions are not safe to analyze."""


@dataclass(frozen=True, slots=True)
class Position:
    symbol: str
    weight: float


@dataclass(frozen=True, slots=True)
class PortfolioValidationResult:
    positions: tuple[Position, ...]
    normalized: bool
    original_weight_sum: float


def validate_positions(
    positions: Sequence[Mapping[str, Any]],
    *,
    normalize: bool = False,
    tolerance: float = 1e-6,
) -> PortfolioValidationResult:
    if not positions:
        raise PortfolioValidationError("at least one position is required")

    parsed: list[Position] = []
    seen: set[str] = set()
    for raw in positions:
        symbol_value = raw.get("symbol")
        if not isinstance(symbol_value, str) or not symbol_value.strip():
            raise PortfolioValidationError("symbol is required")
        symbol = symbol_value.strip().upper()
        if symbol in seen:
            raise PortfolioValidationError(f"duplicate symbol: {symbol}")
        seen.add(symbol)

        weight_value = raw.get("weight")
        if isinstance(weight_value, bool) or not isinstance(weight_value, (int, float)):
            raise PortfolioValidationError(f"weight for {symbol} must be numeric")
        weight = float(weight_value)
        if not math.isfinite(weight) or weight < 0:
            raise PortfolioValidationError(f"weight for {symbol} must be finite and non-negative")
        parsed.append(Position(symbol=symbol, weight=weight))

    total = math.fsum(position.weight for position in parsed)
    if total <= 0:
        raise PortfolioValidationError("weight sum must be positive")

    if normalize:
        normalized_positions = tuple(
            Position(position.symbol, position.weight / total) for position in parsed
        )
        was_normalized = not math.isclose(total, 1.0, abs_tol=tolerance)
        return PortfolioValidationResult(normalized_positions, was_normalized, total)

    if not math.isclose(total, 1.0, abs_tol=tolerance):
        raise PortfolioValidationError(f"weights must sum to 1; got {total:.8f}")
    return PortfolioValidationResult(tuple(parsed), False, total)


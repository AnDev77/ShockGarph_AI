from __future__ import annotations

import math

import pytest
from shockgraph_risk.gjr_garch import GjrParameters, fit_gjr_garch_11, forecast_gjr_garch_11


def test_negative_return_adds_asymmetric_variance_and_multistep_mean() -> None:
    params = GjrParameters(omega=0.00001, alpha=0.1, gamma=0.2, beta=0.6,
                           unconditional_variance=0.00005, training_return_count=120)
    positive = forecast_gjr_garch_11([0.02], params, horizon=1)
    negative = forecast_gjr_garch_11([-0.02], params, horizon=1)
    assert negative ** 2 - positive ** 2 == pytest.approx(0.2 * 0.02 ** 2)
    next_variance = 0.00001 + (0.1 + 0.2) * 0.02 ** 2 + 0.6 * 0.00005
    kappa = 0.1 + 0.6 + 0.2 / 2
    sequence = [next_variance]
    for _ in range(19):
        sequence.append(0.00001 + kappa * sequence[-1])
    assert forecast_gjr_garch_11([-0.02], params, horizon=20) ** 2 == pytest.approx(
        math.fsum(sequence) / 20
    )


def test_fit_is_stationary_and_rejects_invalid_training_returns() -> None:
    returns = [(0.01 if index % 5 else -0.02) * (1 + 0.2 * (index % 3))
               for index in range(125)]
    params = fit_gjr_garch_11(returns)
    assert params.training_return_count == 125
    assert params.gamma >= 0
    assert params.alpha + params.beta + params.gamma / 2 < 1
    assert forecast_gjr_garch_11(returns, params, horizon=5) > 0
    with pytest.raises(ValueError, match="degenerate"):
        fit_gjr_garch_11([0.0] * 120)
    with pytest.raises(ValueError, match="nonfinite"):
        fit_gjr_garch_11([0.01] * 119 + [math.nan])

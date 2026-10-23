"""Zero-mean Gaussian QMLE GJR-GARCH(1,1) for close-to-close log returns.

The gamma/2 long-run contribution assumes symmetric zero-mean innovations.
Historical adjusted-price vintages are not verified by this model.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from scipy.optimize import minimize


@dataclass(frozen=True, slots=True)
class GjrParameters:
    omega: float
    alpha: float
    gamma: float
    beta: float
    unconditional_variance: float
    training_return_count: int


def fit_gjr_garch_11(returns: Sequence[float], *, min_returns: int = 100) -> GjrParameters:
    """Fit a positive stationary asymmetric variance recursion before the holdout."""
    if min_returns < 30 or len(returns) < min_returns:
        raise ValueError("insufficient_training_returns")
    if any(not math.isfinite(value) for value in returns):
        raise ValueError("nonfinite_training_returns")
    scaled = tuple(value * 100 for value in returns)
    variance = math.fsum(value * value for value in scaled) / len(scaled)
    if not math.isfinite(variance) or variance < 1e-10:
        raise ValueError("degenerate_training_returns")

    def objective(vector: Sequence[float]) -> float:
        log_long_run, arch_share, asym_share, persistence = vector
        long_run = math.exp(log_long_run)
        alpha = persistence * arch_share
        gamma = 2 * persistence * (1 - arch_share) * asym_share
        beta = persistence * (1 - arch_share) * (1 - asym_share)
        omega = long_run * (1 - persistence)
        conditional = long_run
        total = 0.0
        for value in scaled:
            total += math.log(conditional) + value * value / conditional
            conditional = (omega + (alpha + (gamma if value < 0 else 0)) * value * value
                           + beta * conditional)
        return total / len(scaled)

    bounds = ((math.log(variance) - 5, math.log(variance) + 5),
              (0.0001, 0.9999), (0.0, 0.9999), (0.001, 0.995))
    starts = ((0.08, 0.0, 0.9), (0.08, 0.2, 0.9), (0.2, 0.5, 0.8),
              (0.4, 0.8, 0.5))
    solutions = [minimize(
        objective, (math.log(variance), share, asym, persistence),
        method="L-BFGS-B", bounds=bounds, options={"maxiter": 400, "ftol": 1e-11},
    ) for share, asym, persistence in starts]
    converged = [result for result in solutions if result.success and math.isfinite(result.fun)]
    if not converged:
        raise ValueError("gjr_fit_did_not_converge")
    fitted = min(converged, key=lambda result: result.fun)
    persistence = float(fitted.x[3])
    share, asym = float(fitted.x[1]), float(fitted.x[2])
    long_run = math.exp(float(fitted.x[0])) / 10_000
    return GjrParameters(
        omega=long_run * (1 - persistence), alpha=persistence * share,
        gamma=2 * persistence * (1 - share) * asym,
        beta=persistence * (1 - share) * (1 - asym),
        unconditional_variance=long_run, training_return_count=len(returns),
    )


def forecast_gjr_garch_11(
    observed_returns: Sequence[float], parameters: GjrParameters, *, horizon: int
) -> float:
    """Forecast root mean future daily variance, filtering only known returns."""
    if horizon < 1 or not observed_returns or any(
        not math.isfinite(value) for value in observed_returns
    ):
        raise ValueError("a positive horizon and observed returns are required")
    conditional = parameters.unconditional_variance
    for value in observed_returns:
        conditional = (parameters.omega + (parameters.alpha + (
            parameters.gamma if value < 0 else 0)) * value * value
            + parameters.beta * conditional)
    persistence = parameters.alpha + parameters.beta + parameters.gamma / 2
    future = []
    for _ in range(horizon):
        future.append(conditional)
        conditional = parameters.omega + persistence * conditional
    forecast = math.sqrt(math.fsum(future) / horizon)
    if not math.isfinite(forecast) or forecast <= 0:
        raise ValueError("nonfinite_gjr_forecast")
    return forecast

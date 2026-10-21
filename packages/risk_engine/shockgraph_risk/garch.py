"""Gaussian quasi-likelihood GARCH(1,1) benchmark for daily close-to-close returns.

The conditional mean is fixed at zero to match the project's squared-return label.
Model parameters must be estimated before the holdout; filtering may then use only
returns known at each forecast origin. This is not the intraday HAR-RV model.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from scipy.optimize import minimize


@dataclass(frozen=True, slots=True)
class GarchParameters:
    omega: float  # daily squared log-return units
    alpha: float
    beta: float
    unconditional_variance: float
    training_return_count: int


def fit_garch_11(returns: Sequence[float], *, min_returns: int = 100) -> GarchParameters:
    """Fit a stationary, zero-mean GARCH(1,1) by Gaussian quasi-likelihood.

    Scale daily log returns to percent for numerical optimization. Optimize the
    long-run variance, persistence, and ARCH share, keeping alpha + beta < 1.
    Multiple fixed starts reduce sensitivity to a single initial parameter guess.
    """
    if min_returns < 30 or len(returns) < min_returns:
        raise ValueError("insufficient_training_returns")
    if any(not math.isfinite(value) for value in returns):
        raise ValueError("nonfinite_training_returns")
    scaled = tuple(value * 100 for value in returns)
    variance = math.fsum(value * value for value in scaled) / len(scaled)
    if not math.isfinite(variance) or variance < 1e-10:
        raise ValueError("degenerate_training_returns")

    def objective(parameters: Sequence[float]) -> float:
        log_variance, arch_share, persistence = parameters
        long_run = math.exp(log_variance)
        alpha = persistence * arch_share
        beta = persistence * (1 - arch_share)
        omega = long_run * (1 - persistence)
        conditional = long_run
        total = 0.0
        for value in scaled:
            total += math.log(conditional) + value * value / conditional
            conditional = omega + alpha * value * value + beta * conditional
        return total / len(scaled)

    bounds = ((math.log(variance) - 5, math.log(variance) + 5),
              (0.0001, 0.9999), (0.001, 0.995))
    solutions = [minimize(
        objective, (math.log(variance), share, persistence),
        method="L-BFGS-B", bounds=bounds,
        options={"maxiter": 400, "ftol": 1e-11},
    ) for share, persistence in ((0.08, 0.9), (0.25, 0.7), (0.5, 0.4))]
    converged = [result for result in solutions if result.success and math.isfinite(result.fun)]
    if not converged:
        raise ValueError("garch_fit_did_not_converge")
    fitted = min(converged, key=lambda result: result.fun)
    long_run = math.exp(float(fitted.x[0])) / 10_000
    persistence = float(fitted.x[2])
    alpha = persistence * float(fitted.x[1])
    beta = persistence * (1 - float(fitted.x[1]))
    return GarchParameters(
        omega=long_run * (1 - persistence), alpha=alpha, beta=beta,
        unconditional_variance=long_run, training_return_count=len(returns),
    )


def forecast_garch_11(
    observed_returns: Sequence[float], parameters: GarchParameters, *, horizon: int
) -> float:
    """Forecast the root mean *future* daily variance for h sessions from t."""
    if horizon < 1 or not observed_returns or any(
        not math.isfinite(value) for value in observed_returns
    ):
        raise ValueError("a positive horizon and observed returns are required")
    conditional = parameters.unconditional_variance
    for value in observed_returns:
        conditional = (parameters.omega + parameters.alpha * value * value
                       + parameters.beta * conditional)
    future_variances = []
    for _ in range(horizon):
        future_variances.append(conditional)
        conditional = parameters.omega + (parameters.alpha + parameters.beta) * conditional
    predicted = math.sqrt(math.fsum(future_variances) / horizon)
    if not math.isfinite(predicted) or predicted <= 0:
        raise ValueError("nonfinite_garch_forecast")
    return predicted

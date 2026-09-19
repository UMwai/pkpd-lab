"""Explicit assumption-based experiments, not fitted population inference."""

import numpy as np
import pandas as pd

from .models import PKParameters, Scenario
from .simulation import simulate

SCALAR_PARAMETERS = (
    "clearance_l_h",
    "central_volume_l",
    "absorption_rate_h",
    "bioavailability",
    "absorption_lag_h",
    "vmax_mg_h",
    "km_mg_l",
)


def with_pk(scenario: Scenario, **changes) -> Scenario:
    """Validated parameter replacement (unlike unchecked model_copy updates)."""
    pk = PKParameters.model_validate(scenario.pk.model_dump() | changes)
    return Scenario.model_validate(scenario.model_dump() | {"pk": pk})


def sensitivity(scenario: Scenario, parameter: str, fraction: float = 0.2) -> pd.DataFrame:
    """One-at-a-time finite perturbation; interaction effects are not represented."""
    if parameter not in SCALAR_PARAMETERS:
        raise ValueError(f"parameter must be one of {SCALAR_PARAMETERS}")
    if not np.isfinite(fraction) or not 0 < fraction < 1:
        raise ValueError("fraction must be between 0 and 1")
    base = getattr(scenario.pk, parameter)
    if base == 0:
        raise ValueError("Multiplicative sensitivity requires a nonzero baseline parameter")
    rows = []
    for factor in (1 - fraction, 1.0, 1 + fraction):
        candidate = with_pk(scenario, **{parameter: base * factor})
        rows.append(
            {
                "parameter": parameter,
                "value": base * factor,
                "factor": factor,
                **simulate(candidate).summary(),
            }
        )
    return pd.DataFrame(rows)


def population(
    scenario: Scenario,
    *,
    subjects: int = 50,
    clearance_cv: float = 0.3,
    volume_cv: float = 0.3,
    seed: int = 42,
) -> pd.DataFrame:
    """Pointwise bands from independent lognormal CL/Vc draws around their medians.

    CV is on the original scale. No residual noise, covariance, covariates,
    parameter-estimation uncertainty, or population fitting is implied.
    """
    if isinstance(subjects, bool) or not isinstance(subjects, int) or not 2 <= subjects <= 500:
        raise ValueError("subjects must be an integer between 2 and 500")
    for cv in (clearance_cv, volume_cv):
        if not np.isfinite(cv) or not 0 <= cv <= 2:
            raise ValueError("CV must be finite and between 0 and 2")
    rng = np.random.default_rng(seed)
    sigma = np.sqrt(np.log1p(np.square([clearance_cv, volume_cv])))
    factors = np.exp(rng.normal(size=(subjects, 2)) * sigma)
    curves = []
    for cl_factor, v_factor in factors:
        candidate = with_pk(
            scenario,
            clearance_l_h=scenario.pk.clearance_l_h * cl_factor,
            central_volume_l=scenario.pk.central_volume_l * v_factor,
        )
        result = simulate(candidate).frame
        curves.append(result.central_mg_l.to_numpy())
    quantiles = np.quantile(curves, [0.05, 0.5, 0.95], axis=0)
    return pd.DataFrame(
        {
            "time_h": result.time_h,
            "p05_mg_l": quantiles[0],
            "p50_mg_l": quantiles[1],
            "p95_mg_l": quantiles[2],
        }
    )

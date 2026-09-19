"""Integrate between dose discontinuities; observe after instantaneous dose events."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp
from scipy.special import expit

from .models import PDParameters, Scenario


def _occupancy(concentration, pd: PDParameters):
    c = np.asarray(concentration)
    with np.errstate(divide="ignore"):
        return expit(pd.hill * (np.log(np.maximum(c, 0)) - np.log(pd.ec50_mg_l)))


def _direct_effect(concentration, pd: PDParameters):
    if pd.model == "linear":
        return pd.baseline + pd.slope_per_mg_l * concentration
    return pd.baseline + pd.maximum_effect * _occupancy(concentration, pd)


@dataclass(frozen=True)
class SimulationResult:
    scenario: Scenario
    frame: pd.DataFrame

    def summary(self) -> dict[str, float]:
        frame = self.frame
        peak = frame.central_mg_l.idxmax()
        return {
            "cmax_sampled_mg_l": float(frame.loc[peak, "central_mg_l"]),
            "tmax_sampled_h": float(frame.loc[peak, "time_h"]),
            "auc_0_end_mg_h_l": float(frame.auc_mg_h_l.iloc[-1]),
            "concentration_end_mg_l": float(frame.central_mg_l.iloc[-1]),
            "max_abs_mass_balance_error_mg": float(frame.mass_balance_error_mg.abs().max()),
        }


def simulate(scenario: Scenario, times=None) -> SimulationResult:
    """Start drug-free at t=0. Output grid includes t=0/end and all dose boundaries.

    Oral F is applied on entry to the depot after the lag; excluded dose is tracked
    separately. Effect-site concentration has no physical mass or volume.
    """
    pk, pd_model, end = scenario.pk, scenario.pd, scenario.end_h
    grid = (
        np.linspace(0, end, scenario.samples) if times is None else np.asarray(times, dtype=float)
    )
    if grid.ndim != 1 or not len(grid) or not np.all(np.isfinite(grid)):
        raise ValueError("times must be a nonempty finite one-dimensional array")
    if np.any(grid < 0) or np.any(grid > end) or np.any(np.diff(grid) <= 0):
        raise ValueError("times must be strictly increasing and within [0, end_h]")

    events: dict[float, list] = {}
    boundaries = {0.0, end}
    for dose in scenario.doses:
        boundaries.add(dose.time_h)
        t = dose.time_h + (pk.absorption_lag_h if dose.route == "oral" else 0.0)
        if t <= end:
            events.setdefault(t, []).append(dose)
            boundaries.add(t)
        if dose.route == "iv_infusion" and dose.time_h + dose.duration_h <= end:
            boundaries.add(dose.time_h + dose.duration_h)
    boundaries = sorted(boundaries)
    grid = np.unique(np.concatenate((grid, boundaries)))
    n = pk.compartments
    # State: depot, n PK amounts, eliminated, cumulative AUC, effect site, response.
    eliminated, auc, effect_site, response = n + 1, n + 2, n + 3, n + 4
    state = np.zeros(n + 5)
    state[response] = pd_model.baseline
    states = np.zeros((len(grid), len(state)))
    volumes = np.array((pk.central_volume_l,) + pk.peripheral_volumes_l)
    q = np.array(pk.intercompartmental_clearances_l_h)

    def rhs(rate):
        def derivative(_time, y):
            d = np.zeros_like(y)
            c = max(y[1] / pk.central_volume_l, 0.0)
            absorb = pk.absorption_rate_h * y[0]
            removal = pk.clearance_l_h * c + pk.vmax_mg_h * c / (pk.km_mg_l + c)
            d[0] = -absorb
            d[1] = absorb + rate - removal
            for j in range(n - 1):
                exchange = q[j] * (y[1] / volumes[0] - y[j + 2] / volumes[j + 1])
                d[1] -= exchange
                d[j + 2] = exchange
            d[eliminated] = removal
            d[auc] = c
            d[effect_site] = pd_model.effect_equilibration_h * (c - y[effect_site])
            if pd_model.model.startswith("indirect"):
                driver = c if pd_model.driver == "plasma" else max(y[effect_site], 0.0)
                modulation = pd_model.maximum_effect * float(_occupancy(driver, pd_model))
                factor = (
                    1 - modulation if pd_model.model == "indirect_inhibition" else 1 + modulation
                )
                d[response] = pd_model.turnover_rate_h * (pd_model.baseline * factor - y[response])
            return d

        return derivative

    for i, start in enumerate(boundaries):
        for dose in events.get(start, []):
            if dose.route == "oral":
                state[0] += dose.amount_mg * pk.bioavailability
            elif dose.route == "iv_bolus":
                state[1] += dose.amount_mg
        states[np.searchsorted(grid, start)] = state
        if i == len(boundaries) - 1:
            break
        stop = boundaries[i + 1]
        rate = sum(
            d.amount_mg / d.duration_h
            for d in scenario.doses
            if d.route == "iv_infusion" and d.time_h <= start < d.time_h + d.duration_h
        )
        sample_indices = np.flatnonzero((grid > start) & (grid <= stop))
        solution = solve_ivp(
            rhs(rate),
            (start, stop),
            state,
            method="LSODA",
            t_eval=grid[sample_indices],
            rtol=1e-8,
            atol=1e-10,
        )
        if not solution.success or not np.all(np.isfinite(solution.y)):
            raise RuntimeError(f"Integration failed on [{start}, {stop}]: {solution.message}")
        states[sample_indices] = solution.y.T
        state = solution.y[:, -1].copy()

    # Account for administered drug, pending lag, and F loss without hiding them.
    administered, pending, unavailable = (np.zeros(len(grid)) for _ in range(3))
    for dose in scenario.doses:
        if dose.route == "iv_infusion":
            administered += dose.amount_mg * np.clip((grid - dose.time_h) / dose.duration_h, 0, 1)
        else:
            administered += dose.amount_mg * (grid >= dose.time_h)
        if dose.route == "oral":
            released = grid >= dose.time_h + pk.absorption_lag_h
            pending += dose.amount_mg * ((grid >= dose.time_h) & ~released)
            unavailable += dose.amount_mg * (1 - pk.bioavailability) * released
    accounted = states[:, : n + 1].sum(axis=1) + states[:, eliminated] + pending + unavailable
    mass_error = accounted - administered
    if np.max(np.abs(mass_error)) > 1e-6 * max(1.0, float(administered[-1])):
        raise RuntimeError("Mass conservation check failed")
    if np.min(states[:, : n + 2]) < -1e-7 * max(1.0, float(administered[-1])):
        raise RuntimeError("Solver produced materially negative drug amounts")
    concentrations = np.maximum(states[:, 1 : n + 1] / volumes, 0)
    ce = np.maximum(states[:, effect_site], 0)
    driver = concentrations[:, 0] if pd_model.driver == "plasma" else ce
    effect = (
        states[:, response]
        if pd_model.model.startswith("indirect")
        else _direct_effect(driver, pd_model)
    )
    data = {
        "time_h": grid,
        "central_mg_l": concentrations[:, 0],
        "effect_site_mg_l": ce,
        "effect": effect,
        "depot_mg": states[:, 0],
        "central_mg": states[:, 1],
        "eliminated_mg": states[:, eliminated],
        "auc_mg_h_l": states[:, auc],
        "administered_mg": administered,
        "pending_lag_mg": pending,
        "unavailable_mg": unavailable,
        "mass_balance_error_mg": mass_error,
    }
    for j in range(n - 1):
        data[f"peripheral_{j + 1}_mg_l"] = concentrations[:, j + 1]
        data[f"peripheral_{j + 1}_mg"] = states[:, j + 2]
    return SimulationResult(scenario, pd.DataFrame(data))

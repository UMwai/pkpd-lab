"""Compile lab equations and solve each subject independently in a common time frame."""

import hashlib
import io
import json
import platform
import time
import zipfile
from dataclasses import dataclass
from importlib.metadata import version

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp

from .expressions import CONCENTRATION, MASS, TIME, Expression, combine, scale, unit_dimension
from .lab_models import Lab, Subject


def lab_hash(lab: Lab) -> str:
    return hashlib.sha256(lab.model_dump_json().encode()).hexdigest()


@dataclass
class CompiledSubject:
    subject: Subject
    expressions: dict[str, Expression]
    algebraic_order: list[str]
    indices: dict[str, int]
    initial: np.ndarray
    equations: list[str]
    units: dict[str, str]

    def environment(self, t, state):
        values = {p.symbol: p.value for p in self.subject.parameters} | {"t": t}
        for c in self.subject.compartments:
            amount = max(float(state[self.indices[c.symbol]]), 0)
            values[c.symbol], values[f"{c.symbol}_C"] = amount, amount / c.volume_l
        for e in self.subject.equations:
            if e.derivative_order:
                values[e.symbol] = float(state[self.indices[e.symbol]])
                for j in range(1, e.derivative_order):
                    values[f"{e.symbol}_d{j}"] = float(state[self.indices[f"{e.symbol}_d{j}"]])
        for symbol in self.algebraic_order:
            values[symbol] = self.expressions[symbol].evaluate(values)
        return values


def compile_subject(subject: Subject) -> CompiledSubject:
    if not subject.compartments and not subject.equations:
        raise ValueError(f"{subject.name}: add a compartment or equation before generating")
    dimensions = {"t": TIME} | {p.symbol: unit_dimension(p.unit) for p in subject.parameters}
    indices, initial, units, lines = {}, [], {"time_h": "h"}, []
    for c in subject.compartments:
        dimensions[c.symbol], dimensions[f"{c.symbol}_C"] = MASS, CONCENTRATION
        indices[c.symbol] = len(initial)
        initial.append(c.initial_mg)
        units[c.symbol], units[f"{c.symbol}_C"] = "mg", "mg/L"
        lines.append(f"{c.symbol}_C = {c.symbol} / {c.volume_l:g} L")
    for e in subject.equations:
        dimensions[e.symbol] = unit_dimension(e.unit)
        units[e.symbol] = e.unit
        for j in range(e.derivative_order):
            symbol = e.symbol if j == 0 else f"{e.symbol}_d{j}"
            dimensions[symbol] = combine(dimensions[e.symbol], scale(TIME, j), -1)
            indices[symbol] = len(initial)
            initial.append(e.initial[j])
            units[symbol] = e.unit if j == 0 else f"({e.unit})/h^{j}"
    expressions = {}
    for e in subject.equations:
        expected = combine(dimensions[e.symbol], scale(TIME, e.derivative_order), -1)
        try:
            expressions[e.symbol] = Expression.compile(e.rhs, dimensions, expected)
        except ValueError as exc:
            raise ValueError(f"{subject.name} / {e.symbol}: {exc}") from exc
        lhs = (
            e.symbol
            if e.derivative_order == 0
            else f"d^{e.derivative_order}{e.symbol}/dt^{e.derivative_order}"
        )
        lines.append(f"{lhs} = {e.rhs}    [({e.unit})/h^{e.derivative_order}]")
    remaining = {e.symbol for e in subject.equations if e.derivative_order == 0}
    algebraic_order = []
    while remaining:
        ready = sorted(s for s in remaining if not (expressions[s].references & remaining))
        if not ready:
            raise ValueError(
                "Algebraic equations contain a cycle; implicit DAE systems are not supported"
            )
        algebraic_order.extend(ready)
        remaining.difference_update(ready)
    compartment_terms = {c.symbol: [] for c in subject.compartments}
    for i, process in enumerate(subject.processes, 1):
        rate = f"r{i}"
        lines.append(
            f"{rate} = {process.coefficient:g} [{process.coefficient_unit}] "
            f"* {process.source}_C^{process.kinetic_order}    [mg/h]"
        )
        compartment_terms[process.source].append(f"-{rate}")
        if process.target:
            compartment_terms[process.target].append(f"+{rate}")
    for symbol, terms in compartment_terms.items():
        lines.append(f"d{symbol}/dt = {' '.join(terms) or '0'}    [mg/h]")
    for e in subject.equations:
        for j in range(e.derivative_order - 1):
            left = e.symbol if j == 0 else f"{e.symbol}_d{j}"
            lines.append(f"d{left}/dt = {e.symbol}_d{j + 1}")
    initial.append(0.0)  # Physical elimination ledger; excluded from custom variables.
    return CompiledSubject(
        subject, expressions, algebraic_order, indices, np.array(initial), lines, units
    )


def generate_lab(lab: Lab) -> dict:
    if not lab.subjects:
        raise ValueError("Add at least one subject before generating a lab")
    compiled = [compile_subject(subject) for subject in lab.subjects]
    return {
        "lab_sha256": lab_hash(lab),
        "subjects": [
            {
                "id": c.subject.id,
                "name": c.subject.name,
                "equations": c.equations,
                "units": c.units,
                "initial_state": {
                    name: float(c.initial[index]) for name, index in c.indices.items()
                },
                "dose_events": [d.model_dump() for d in c.subject.doses],
            }
            for c in compiled
        ],
        "conventions": {
            "time_unit": "h",
            "dose_values": "post-dose",
            "subjects": "independent; no cross-subject transfer",
            "custom_equations": "do not add physical drug mass",
            "zero_order": "availability-limited at depletion; pulse and continuous refill",
            "zero_reactivation_mg": "1e-9 * max(1, subject initial + total dosed mg)",
        },
    }


def _simulate_subject(compiled, lab):
    subject = compiled.subject
    state = compiled.initial.copy()
    bounds = sorted({0.0, lab.end_h, *(d.time_h for d in subject.doses)})
    zero_sources = {
        p.source for p in subject.processes if p.kinetic_order == 0 and p.coefficient > 0
    }
    endpoints, segments = {}, []
    deadline, evaluations = time.monotonic() + 15, 0
    disabled = set()
    volumes = {c.symbol: c.volume_l for c in subject.compartments}
    zero_order = subject.zero_source_order()
    reactivation_mg = 1e-9 * max(
        1, sum(c.initial_mg for c in subject.compartments) + sum(d.amount_mg for d in subject.doses)
    )

    def fluxes(y):
        rates = [
            p.coefficient
            * (max(float(y[compiled.indices[p.source]]), 0) / volumes[p.source]) ** p.kinetic_order
            for p in subject.processes
        ]
        # Empty sources can pass on arriving drug, but cannot create unavailable mass.
        for source in zero_order:
            if source not in disabled:
                continue
            outgoing = [i for i, p in enumerate(subject.processes) if p.source == source]
            demand = sum(rates[i] for i in outgoing)
            supply = sum(rates[i] for i, p in enumerate(subject.processes) if p.target == source)
            if demand > supply:
                for i in outgoing:
                    rates[i] *= supply / demand
        return rates

    def rhs(t, y):
        nonlocal evaluations
        evaluations += 1
        if evaluations > 100000 or time.monotonic() > deadline:
            raise ValueError(
                "Simulation resource limit reached; shorten the horizon or revise the model"
            )
        d = np.zeros_like(y)
        for process, rate in zip(subject.processes, fluxes(y), strict=True):
            source_index = compiled.indices[process.source]
            d[source_index] -= rate
            d[compiled.indices[process.target] if process.target else -1] += rate
        values = compiled.environment(t, y)
        for e in subject.equations:
            if not e.derivative_order:
                continue
            base = compiled.indices[e.symbol]
            for j in range(e.derivative_order - 1):
                d[base + j] = y[base + j + 1]
            d[base + e.derivative_order - 1] = compiled.expressions[e.symbol].evaluate(values)
        if not np.all(np.isfinite(d)):
            raise ValueError("Model produced nonfinite rates")
        return d

    for i, start in enumerate(bounds):
        for dose in subject.doses:
            if dose.time_h == start:
                state[compiled.indices[dose.target]] += dose.amount_mg
        disabled = {s for s in zero_sources if state[compiled.indices[s]] <= 0}
        endpoints[start] = state.copy()
        if i == len(bounds) - 1:
            break
        stop, cursor, iterations = bounds[i + 1], start, 0
        while cursor < stop:
            events, sources = [], sorted(zero_sources)
            releasing = set(disabled)
            for symbol in sources:
                threshold = reactivation_mg if symbol in releasing else 0

                def depletion(t, y, index=compiled.indices[symbol], threshold=threshold):
                    return y[index] - threshold

                depletion.terminal = True
                depletion.direction = 1 if symbol in releasing else -1
                events.append(depletion)
            solution = solve_ivp(
                rhs,
                (cursor, stop),
                state,
                method="DOP853",
                rtol=1e-8,
                atol=1e-10,
                dense_output=True,
                events=events or None,
            )
            if not solution.success or not np.all(np.isfinite(solution.y)):
                raise ValueError(f"Solver failed for {subject.name}: {solution.message}")
            reached = float(solution.t[-1])
            segments.append((cursor, reached, solution.sol))
            state = solution.y[:, -1].copy()
            if solution.status == 1:
                for symbol, hits in zip(sources, solution.t_events, strict=True):
                    if len(hits):
                        if symbol in releasing:
                            disabled.remove(symbol)
                        else:
                            state[compiled.indices[symbol]] = 0.0
                            disabled.add(symbol)
                for symbol in sources:
                    if state[compiled.indices[symbol]] <= 0:
                        state[compiled.indices[symbol]] = 0
                        disabled.add(symbol)
            endpoints[reached] = state.copy()
            cursor = reached
            iterations += 1
            if iterations > 2000:
                raise ValueError("Could not resolve compartment depletion events")
    grid = np.unique(np.concatenate((np.linspace(0, lab.end_h, lab.samples), list(endpoints))))
    states = np.zeros((len(grid), len(state)))
    for start, stop, solution in segments:
        mask = (grid > start) & (grid <= stop)
        if mask.any():
            states[mask] = solution(grid[mask]).T
    for t, y in endpoints.items():
        states[np.searchsorted(grid, t)] = y
    administered = sum(c.initial_mg for c in subject.compartments) + np.zeros(len(grid))
    for dose in subject.doses:
        administered += dose.amount_mg * (grid >= dose.time_h)
    physical = states[:, : len(subject.compartments)]
    mass_error = physical.sum(axis=1) + states[:, -1] - administered
    scale_mg = max(1.0, float(administered[-1]))
    if np.max(np.abs(mass_error)) > 1e-6 * scale_mg:
        raise ValueError("Physical compartment mass conservation failed")
    if physical.size and physical.min() < -1e-7 * scale_mg:
        raise ValueError("Model produced materially negative compartment amounts")
    data = {"time_h": grid}
    environments = [compiled.environment(t, y) for t, y in zip(grid, states, strict=True)]
    for symbol in compiled.units:
        if symbol != "time_h":
            data[symbol] = [env[symbol] for env in environments]
    data.update(
        eliminated_mg=states[:, -1],
        initial_plus_dosed_mg=administered,
        mass_balance_error_mg=mass_error,
    )
    return pd.DataFrame(data)


def simulate_lab(lab: Lab) -> dict[str, pd.DataFrame]:
    generate_lab(lab)  # Validate every subject before starting any solve.
    results = {}
    for subject in lab.subjects:
        try:
            results[subject.id] = _simulate_subject(compile_subject(subject), lab)
            results[subject.id].attrs["lab_sha256"] = lab_hash(lab)
        except (ArithmeticError, ValueError) as exc:
            raise ValueError(f"{subject.name}: {exc}") from exc
    return results


def export_run(lab: Lab, results: dict[str, pd.DataFrame]) -> bytes:
    expected = {s.id for s in lab.subjects}
    if set(results) != expected:
        raise ValueError("Run results do not match lab subjects")
    if any(frame.attrs.get("lab_sha256") != lab_hash(lab) for frame in results.values()):
        raise ValueError("Run results belong to a different lab configuration")
    manifest = generate_lab(lab)
    manifest["versions"] = {
        p: version(p) for p in ("pkpd-lab", "numpy", "scipy", "pandas", "pydantic")
    }
    manifest["python"] = platform.python_version()
    manifest["platform"] = platform.platform()
    manifest["solver"] = {"method": "DOP853", "rtol": 1e-8, "atol": 1e-10}
    manifest["output_sha256"] = {}
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("lab.json", lab.model_dump_json(indent=2))
        for subject in lab.subjects:
            filename = f"subjects/{subject.id}.csv"
            payload = results[subject.id].to_csv(index=False).encode()
            archive.writestr(filename, payload)
            manifest["output_sha256"][filename] = hashlib.sha256(payload).hexdigest()
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    return bundle.getvalue()

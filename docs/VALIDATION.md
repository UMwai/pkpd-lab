# Validation record

The initial suite verifies the mathematical implementation with synthetic
experiments. It does not establish empirical or clinical validity.

| Check | Independent reference or failure being tested |
| --- | --- |
| One-compartment IV bolus | Exponential concentration and exact integrated AUC |
| One-compartment oral | Bateman function, including the ka=ke limiting case |
| Two- and three-compartment IV | Independently assembled linear system and matrix exponential |
| Repeated off-grid boluses | Analytical superposition, exact event insertion, post-dose values |
| Overlapping finite infusions | Analytical infusion superposition and delivered amount |
| Lag and bioavailability | Pending dose/F loss accounted exactly once |
| Bolus at horizon | Final concentration jumps without adding finite-horizon AUC |
| Pure saturable elimination | Integrated Michaelis–Menten implicit amount/time relation |
| Mixed routes and nonlinear PK | Mass conservation across 1, 2, and 3 compartments |
| Effect compartment | Exact biexponential effect-site solution |
| Indirect response | Exact constant-driver turnover solutions and no-drug baseline |
| Input failures | Nonfinite/negative parameters, invalid structures, routes, and observation grids |
| Reproducibility | Seeded population draws, JSON round trips, CLI metadata and scenario hash |
| Workbench | Startup, model/route changes, indirect response, population and sensitivity actions |

Run `uv run pytest` for the current result; CI runs the suite on Python
3.11, 3.12, and 3.13. Numerical comparison tolerances are explicit in each test.
Locked library versions are in `uv.lock`; no unsupported numerical equivalence
claim is made against NONMEM, mrgsolve, Monolix, or Torsten.

Before admitting a named drug model, add an evidence record with the full source,
equations, parameter definitions and units, formulation/route, study population,
data availability, parameter uncertainty, and limitations. Reproduce published
predictions and use independent observations when available. Separate source
reproduction, numerical verification, parameter estimation, predictive checking,
and prospective validation in that record.

# Validation record

The initial suite verifies the mathematical implementation with synthetic
experiments. It does not establish empirical or clinical validity.

## Dated baseline

On 2026-09-20, a fresh local run against engine revision
`08e253269ea2062e17ceacdfce9f252b761c2eea` passed all **59** original tests plus
the required lint and format checks. The published baseline
[CI run](https://github.com/UMwai/pkpd-lab/actions/runs/35473293511)
passed on Python 3.11, 3.12, and 3.13. These are dated receipts, not a claim about
unreviewed later changes. The UI refresh adds separate presentation tests.

The 2026-09-20 UI/documentation refresh passed **65 tests**, lint, and formatting.
New checks cover non-mutating bolus/log plotting, the three-compartment diagram,
import-mode control visibility, conditional linear-PD controls, and explicit
comparison/population failure messages. Separate Chromium checks passed desktop
rendering, model comparison, population execution/export, scenario import/export
round trip, invalid-import handling, and 390-pixel mobile rendering with no page
errors. The example scenarios were rerun, local documentation links resolved, and
the checked-in scenario JSON schema matched the Python model.

These browser checks did not exercise editable-grid cell changes or establish
full accessibility compliance. The updated screenshot is an illustration of the
rendered workbench, not scientific validation evidence.

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

## Lab builder v0.2

The 2026-09-20 lab-builder implementation passed **102 tests**, the required
lint/format checks, and wheel/source-distribution builds. Both checked-in lab
examples ran through the CLI; the clearance example also generated a model
manifest. This extends the original 65-test suite with the following checks:

| Check | Independent reference or failure being tested |
| --- | --- |
| Kinetic orders 0–3 | Analytical single-compartment elimination solutions |
| Zero-order transfer | Exact depletion, conservation, and pulse refill |
| Zero-order elimination with absorption | Analytical central trajectory before/after depletion, including continuous inflow |
| PK starting templates | Trajectories compared with the existing 1-, 2-, and 3-compartment engine |
| Derivative orders 1–3 | Polynomial solutions and initial derivative values |
| Higher-order coupling | Harmonic oscillator and dependency-ordered algebraic outputs |
| Model generation | Unit mismatches, unsafe expressions, unresolved symbols, and algebraic cycles rejected |
| Isolation and provenance | Independent subjects, configuration hashes, and stale-run export rejection |
| Local labs and CLI | Save/reopen, import size/ID checks, run archives, and output overwrite refusal |
| UI lifecycle | Create/add/clone, generate/run, local save/reopen, and stale-result invalidation |

Separate Chromium checks edited a compartment volume in the actual grid, applied
the change, generated and ran both subjects, and verified the downloaded ZIP's
lab JSON and two subject CSVs. Export/import into a fresh browser session preserved
the edited lab exactly. Desktop and 390-pixel layouts rendered without page errors
or horizontal page overflow. The checked-in lab screenshot reflects this synthetic
editing exercise. These checks do not establish full accessibility compliance.

The lab guide records solver tolerances, depletion/refill conventions, resource
limits, and unsupported model classes. Reference solutions cover selected
synthetic systems; they do not establish accuracy for every user-written model.

## Coverage limits and pending checks

- Indirect-response analytical tests use a plasma driver; indirect response with
  the effect-site driver has no independent reference-solution test.
- Non-unit Hill coefficients and linear PD with nonzero exposure lack reference
  tests. The no-drug baseline tests do not establish those behaviors.
- Combined linear/saturable elimination and nonlinear peripheral-distribution
  cases have mass-balance checks, not independent trajectory comparisons.
- The suite does not establish accuracy/runtime for thousands of doses, extreme
  stiff parameter combinations, or very different scales across state variables.
- Streamlit AppTest covers several controls and state invalidation, but not
  file uploads or editable-grid cell interactions. Browser import/export checks
  are separate from the automated suite; a screenshot alone does not verify them.
- No actual drug concentration dataset, prospective outcome, or cross-engine
  benchmark has been validated. Reference citations are not numerical benchmarks.

Fable 5.1's [static review](reviews/2026-09-20-fable-5.1.md) identified these
gaps. It did not execute the suite or validate a drug model.

Before admitting a named drug model, add an evidence record with the full source,
equations, parameter definitions and units, formulation/route, study population,
data availability, parameter uncertainty, and limitations. Reproduce published
predictions and use independent observations when available. Separate source
reproduction, numerical verification, parameter estimation, predictive checking,
and prospective validation in that record.

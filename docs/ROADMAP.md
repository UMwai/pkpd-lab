# Research roadmap

## Delivered: v0.2 lab builder

The lab hierarchy, local JSON persistence, independent subjects, editable
compartment networks, power-law kinetic orders 0–3, explicit derivative orders
0–3, dimensional checking, model generation, and run exports are implemented.
See [LAB_BUILDER.md](LAB_BUILDER.md) for the contract and limitations.
This extends model construction; it does not establish empirical drug validity.

Next lab-specific extensions are finite infusion/lag events, validated feedback
from custom states into physical fluxes, per-state solver tolerances, and broader
independent checks for stiff networks. General implicit DAE systems and cycles
among zero-order sources require a separately tested solver strategy.

The first release establishes a general simulator. The next steps should be
driven by a specific scientific question and the data that can resolve it.

## Immediate priorities after the Fable 5.1 review

Before expanding the biological scope, close the baseline's documented gaps:

1. Add independent trajectory references for effect-site-driven indirect response,
   non-unit Hill slopes, exposed linear PD, and combined nonlinear/distribution
   models. Benchmark long dose histories and scale-dependent solver behavior.
2. Extend experiment receipts with Python/platform, pandas, Git revision, lockfile
   and output hashes; archive population draws and their dependency versions.
3. Introduce a version 2 schema with explicit `_per_h` rate-constant names and an
   explicit migration from version 1. Do not silently reinterpret existing fields.
4. Improve between-grid peak estimation while retaining sampled Cmax/Tmax, then
   assess component-specific tolerances and event-time representations with tests.
5. Admit one published model using the evidence record below.

The UI refresh improves control organization, model topology, and bolus plotting;
it does not close the scientific verification gaps. See the
[review disposition](reviews/2026-09-20-fable-5.1.md).

## 1. Admit published drug models

Add a versioned model registry with source DOI/URL, parameter table, units,
population, formulation, route, assay/matrix, active moiety, and extraction notes.
Retain alternative published parameterizations instead of averaging them without
justification. Record source reproduction and predictive validation separately.
Start with one well-documented small molecule with accessible concentration-time
data and both oral and IV characterization if possible.

## 2. Fit observed data and evaluate model adequacy

Define a tidy observation schema: subject ID, actual sampling/dose time, analyte,
concentration, units, assay/LLOQ, censoring flag, dosing history, and covariates.
Then add bounded individual fitting, additive/proportional error models, residual
plots, likelihood-based diagnostics, parameter profiles, and uncertainty intervals.
Handle below-quantification observations explicitly rather than replacing them
with zero. Evaluate identifiability before estimating F, ka, CL, volumes, and
additional compartments together. Reserve data for predictive checks.

## 3. Expand absorption and disposition

- Transit compartments, zero-order/combined input, extended-release dissolution,
  food/formulation scenarios, and enterohepatic recirculation where supported.
- Parent–metabolite models with molecular-weight-aware mass accounting and
  metabolite-specific elimination and effects.
- Protein binding and unbound exposure, separating plasma and whole-blood units.
- Mechanistic drug interactions, enzyme turnover, time-varying clearance,
  autoinduction, and inhibition only with an explicit interaction model.
- Target-mediated drug disposition for relevant biologics; avoid treating a
  generic saturable pathway as a validated target-binding model.

## 4. Model populations and covariates

Add weight/allometric, renal/hepatic-function, age, and other covariate relationships
with explicit applicable populations and evidence. Introduce correlated random
effects, between-occasion variability, parameter uncertainty, and measurement
noise as distinct sources. Consider a Stan/Torsten or other established
mixed-effects estimation backend rather than calling simple Monte Carlo a fitted
population PK model.

## 5. Extend PD and mechanistic scope

Add response-loss turnover variants, receptor binding/occupancy, tolerance,
feedback, disease progression, and separate efficacy/adverse-effect endpoints.
Connect models to measured biomarkers and endpoints before implying therapeutic
benefit. PBPK requires explicit organ volumes, flows, tissue partitioning,
physiology, and validation; extra abstract compartments alone do not make PBPK.

## 6. Strengthen research workflows

Add batch scenario sweeps, formal global sensitivity, sampling-design experiments,
validated terminal slope/NCA methods, and an explicit steady-state convergence
criterion. Expand solver stress testing, cross-engine benchmarks, and archived
reproduction datasets. Add saved experiments with data access controls before
supporting shared deployments or patient-level datasets.

No fitting, named drug calibration, PBPK, or clinical dosing recommendation is
part of v0.1. These are explicit extension tasks, not implemented capabilities.

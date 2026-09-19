# Research roadmap

The first release establishes a general simulator. The next steps should be
driven by a specific scientific question and the data that can resolve it.

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

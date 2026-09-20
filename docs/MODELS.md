# Models and numerical conventions

## State, units, and interpretation

The PK state contains an absorption depot `Ag`, central amount `Ac`, and zero to
two peripheral amounts `Ap_i`, all in mg. `Cc = Ac/Vc` and `Cp_i = Ap_i/Vp_i`
are in mg/L. The effect site `Ce` is a virtual concentration in mg/L, not an
additional physical compartment; it does not remove drug from central mass.

All volumes are positive, CL and Q are nonnegative, absorption and PD rate
constants are positive, and F is in [0,1]. Nonfinite values, unknown fields,
inconsistent volume/Q tuples, and unsupported routes are rejected.

**Version 1 naming caveat:** `absorption_rate_h`, `effect_equilibration_h`, and
`turnover_rate_h` all contain rate constants in **1/h**, despite their `_h`
suffix. They are not durations or half-lives. `time_h`, `duration_h`, `end_h`, and
`absorption_lag_h` are durations/times in hours. The planned version 2 schema will
use explicit `_per_h` names with a version 1 migration; v0.1 keeps its existing
field names so saved scenarios remain loadable.

The model is a mammillary system: each peripheral compartment exchanges only
with the central compartment. Three PK compartments means central plus two
peripherals, not three organs and not depot + central + peripheral.

## Pharmacokinetics

Between dose events:

```text
dAg/dt    = -ka * Ag
dAc/dt    = ka * Ag + infusion_rate - CL * Cc
            - Vmax * Cc/(Km + Cc) - sum_i Q_i * (Cc - Cp_i)
dAp_i/dt  = Q_i * (Cc - Cp_i)
dAelim/dt = CL * Cc + Vmax * Cc/(Km + Cc)
dAUC/dt   = Cc
```

`Vmax` is mg/h; `Km` is mg/L. By default Vmax=0. With Vmax>0 the saturable
pathway is additive to CL. Set CL=0 for pure Michaelis–Menten elimination.

An oral dose at `td` enters the depot as `F*dose` at `td + lag`. Before release,
the entire dose is tracked as pending lag. At release, `(1-F)*dose` is tracked
as unavailable, representing the aggregate loss captured by F. This is an
accounting convention, not a mechanistic gut/liver first-pass model. First-order
absorption begins after the lag. F and lag apply only to oral administration.

An IV bolus instantaneously increases Ac by the dose amount. An infusion supplies
`amount/duration` to Ac on `[td, td+duration)`. Rates add when infusions overlap.
The administered amount during a partial infusion is only what has been delivered.

Mass accounting at every output time:

```text
administered = pending_lag + unavailable + Ag + Ac + sum(Ap_i) + Aelim
```

Simulation raises on material conservation failures or negative PK amounts.
Tiny solver roundoff in concentrations is clipped at zero for output; raw amount
states remain available, and conservation is checked before display clipping.

## Pharmacodynamics

For an effect-site driver:

```text
dCe/dt = ke0 * (Cc - Ce)
```

For a plasma driver, `Cdriver = Cc`; otherwise `Cdriver = Ce`.

```text
occupancy = Cdriver^hill / (EC50^hill + Cdriver^hill)
Emax:     E = baseline + maximum_effect * occupancy
Linear:   E = baseline + slope * Cdriver
```

Occupancy is evaluated in log space for numerical stability. A negative
`maximum_effect` represents a decreasing direct response; the model does not
impose a physiological floor on direct Emax or linear outputs. EC50 denotes the
half-maximal concentration of the selected driver, not necessarily measured plasma.
Response units are user-defined and shown as arbitrary units in the workbench.

Turnover models modify **production** of the response, with `kin = kout*baseline`:

```text
Inhibition:  dR/dt = kout * baseline * (1 - Imax*occupancy) - kout*R
Stimulation: dR/dt = kout * baseline * (1 + Smax*occupancy) - kout*R
R(0) = baseline
```

`maximum_effect` is Imax in [0,1] or Smax >=0 for these models; the baseline must
be positive. These are two specific indirect-response structures. Inhibition or
stimulation of response loss, tolerance, and disease progression are not included.

## Event and solver conventions

- The system starts drug-free at t=0. Full prior dosing must be represented;
  arbitrary initial concentrations and implicit steady-state initialization are
  not currently supported.
- All administration, delayed absorption, and infusion-stop times within the
  horizon are solver boundaries. Simultaneous boluses sum; records need not be sorted.
- SciPy LSODA integrates each continuous segment with `rtol=1e-8`, `atol=1e-10`.
  Solver failure stops the experiment; there is no fallback to synthetic output.
  The same absolute tolerance applies to amount, AUC, effect-site, and response
  states despite their different units. Accuracy at untested scales is not established.
- Output is the sorted union of the requested grid, event boundaries, zero, and
  the horizon. Explicit observation times must be finite, unique, increasing,
  nonempty, and within the closed interval `[0, end_h]`.
- Exact bolus observations are post-dose. A dose at the horizon contributes to
  the final concentration but contributes no additional finite-horizon AUC.
- A dose after the horizon is rejected. An infusion or absorption lag may extend
  beyond it; only delivered/released drug is accounted for within the horizon.
- Cmax/Tmax use the output samples and can miss between-grid extrema. The current
  workbench breaks concentration lines at IV bolus times instead of drawing a
  ramp across the jump. These visual gaps do not change simulated values or AUC;
  they do not supply a separate pre-dose observation. See the exact event ledger.

## Comparisons and variability

Structural comparisons hold the central and absorption parameters fixed while
changing peripheral distribution. They do not fit models or rank their support
from observations; a better-looking curve is not evidence for more compartments.

Population experiments independently sample CL and Vc with
`parameter = typical * exp(N(0, log(1+CV^2)))`, where the second Normal argument
denotes **variance**. Typical values are medians, not arithmetic means. Other
parameters are fixed. The RNG is seeded, and the outputs are pointwise 5th,
50th, and 95th percentiles. No covariance, residual variability, or estimation
uncertainty is implied. CL=0 remains zero under multiplicative variability.
Quantiles use NumPy's default linear interpolation. Estimated band edges have
Monte Carlo sampling error, especially with small subject counts; a fixed seed
makes the draws reproducible, not precise. Increase subject count and compare
seeds when investigating band stability.

By default, sensitivity uses three input-validated scenarios at 0.8, 1.0, and 1.2 times one
parameter. This does not measure interactions or constitute global sensitivity.
Invalid perturbations (for example F>1) are rejected rather than silently clipped.

## Limits when moving to real drugs

Oral-only observations generally identify apparent CL/F and V/F without
additional information about F. Do not insert published apparent values as
absolute CL and V while independently applying F without reconciling the
parameterization. Central volume, distribution volume, unbound concentration,
whole-blood/plasma measurements, active moiety, and parent/metabolite units must
also be distinguished. Absorption can control the apparent terminal slope
(flip-flop kinetics), so `ln(2)*Vc/CL` is not a general terminal half-life here.

The engine currently lacks explicit metabolites, protein-binding dynamics,
transit absorption, formulation dissolution, enzyme induction/inhibition, organ
physiology, patient covariate models, and concentration-dependent distribution.
See the roadmap and references before adding these mechanisms.

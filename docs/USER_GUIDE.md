# Running and reproducing an experiment

This guide describes v0.1 behavior. Bundled scenarios are synthetic; named-drug
calibration, observed-data fitting, and patient-specific recommendations are not
implemented. For equations and assumptions, see [MODELS.md](MODELS.md).

## Start the workbench

From a clone of this repository:

```bash
uv sync --locked
uv run streamlit run app.py
```

Open `http://localhost:8501`. If that port is occupied, choose another explicitly:

```bash
uv run streamlit run app.py --server.port 8517
```

That command serves the workbench locally at `http://localhost:8517`. Publishing
the GitHub repository does not deploy a shared web application. The process must
remain running; restart it after closing the terminal or rebooting.

## Build and inspect a scenario

1. Select **Build a scenario**, then choose 1, 2, or 3 PK compartments.
   Each extra compartment adds a peripheral volume and a distribution clearance Q.
2. Choose oral, IV bolus, or IV infusion administration. Set dose amount, count,
   interval, and the simulation horizon. Infusions require a positive duration.
3. Under **Distribution & clearance**, set CL and central volume.
   Under **Absorption & elimination**, adjust ka, F,
   and lag for oral doses. Saturable elimination adds to CL; use CL=0 for a pure
   saturable model.
4. Choose a PD response and its plasma or effect-site driver. For Emax,
   `maximum_effect` is a signed change in response units. For indirect inhibition
   it is a fraction in [0,1]; for indirect stimulation it is a nonnegative
   fractional increase in production. Linear response uses `slope_per_mg_l`.
5. Inspect **Trajectories**, its dose schedule, and **Mass accounting & interpretation**.
   Keep the horizon long enough to answer the research question. The terminal
   concentration is a value at the chosen horizon, not an automatic trough or
   steady-state measurement.

The time origin is simulation t=0, even if the first administration is later.
Read Cmax/Tmax over the entire simulated history, not as first-dose or per-interval
statistics. For equal sampled maxima, the earliest output time is reported.

### Custom schedules and missed doses

Enable **Edit individual dose events** to edit `time_h`, `amount_mg`, `route`, and
`duration_h`, or add/delete rows. Delete a missed event; do not replace its amount
with zero because dose amounts must be positive. Mixed routes, loading doses, and
overlapping infusions are permitted. Non-infusion rows must have duration zero.
All administration times must fall within the horizon. An infusion or oral lag
can finish after the horizon.

### Compare model structures

**Compare models** holds dose history, central volume, clearance, absorption,
and PD settings fixed while adding or removing peripheral compartments. Added
peripherals use V1=30 L/Q1=6 L/h and V2=80 L/Q2=3 L/h unless those parameters are
already present in the scenario. Consequently, total distribution volume changes
across these comparisons. This is not a comparison of independently fitted models
or evidence that one compartment count describes a real drug better.

### Explore variability and sensitivity

**Run virtual population** varies only CL and central volume, independently, with
lognormal draws. Scenario values are distribution medians. Specify both CVs,
subject count, and seed; export both the bands CSV and assumptions JSON. The
workbench permits 10–200 subjects and CVs of 0–1; the Python API permits 2–500
subjects and CVs of 0–2. Neither provides population fitting or measurement noise.

The sensitivity button compares 80%, 100%, and 120% of CL, Vc, or ka. The API also
supports F, lag, Vmax, and Km with a configurable fractional change. Multiplicative
sensitivity at a zero baseline is rejected, as are parameter changes outside valid
bounds. An oral-only parameter such as ka has no PK effect on a purely IV history.
Results persist across unrelated UI reruns and are hidden when their input
assumptions change; rerun the experiment to generate results for the new inputs.

## Save, import, and reproduce

In **Experiment record**, download the scenario JSON and trajectory CSV. To restore
the scenario, choose **Import JSON** and upload the standalone scenario. Imported
parameters, dose events, sampling grid, and provenance take precedence; the
sidebar builder is hidden. To edit an imported scenario, edit its JSON or use the Python
API and re-import it; the sidebar does not edit the imported object.

`schema_version` is currently 1. Missing fields receive model defaults; unknown
fields are rejected by the Python model. [scenario.schema.json](scenario.schema.json)
describes the serialized structure, but cross-field rules such as matching
peripheral/Q counts and dose/horizon consistency are enforced by the Python
validators. A JSON-schema check alone is insufficient.

Run the downloaded JSON through the CLI to produce a reproducibility receipt:

```bash
uv run pkpd examples/repeated_oral.json --output outputs/repeated_oral.csv
```

This writes the trajectory and `outputs/repeated_oral.json`. Use a fresh `.csv`
output path: existing files are overwritten, and choosing a `.json` output path
would collide with the companion receipt. Keep outputs separate from input files.
The companion receipt contains:

| Field | Meaning |
| --- | --- |
| `scenario` | Resolved, validated scenario with defaults included |
| `scenario_sha256` | Hash of `Scenario.model_dump_json()` encoded as UTF-8 |
| `versions` | pkpd-lab, NumPy, SciPy, and Pydantic versions |
| `solver` | LSODA method, relative tolerance, and absolute tolerance |
| `summary` | Sampled Cmax/Tmax, AUC through the horizon, final concentration, mass residual |

The scenario hash is serialization-specific, not a hash of the original file or
a canonical scientific experiment identity. Reordering dose records can change
the hash even when it leaves the simulation unchanged. The receipt does not
include the Git commit, lockfile hash, full platform information, or an output
file hash; archive the commit and `uv.lock` with experiments that need those details.
The UI trajectory/scenario downloads do not contain CLI version/solver receipts.
Population exports include assumptions and a seed, but not individual parameter
draws or dependency versions.

Extract a standalone scenario from a CLI receipt before importing it into the UI:

```bash
uv run python - <<'PY'
import json
from pathlib import Path

receipt = json.loads(Path("outputs/repeated_oral.json").read_text())
Path("outputs/restored-scenario.json").write_text(
    json.dumps(receipt["scenario"], indent=2) + "\n"
)
PY
```

## Python observations and exported columns

```python
from pkpd_lab import Scenario, simulate

result = simulate(Scenario(), times=[0.0, 0.5, 2.0, 8.0, 24.0, 48.0])
print(result.frame)
```

Passing `times` replaces the uniform grid; the solver still adds zero, the horizon,
and all event boundaries. Match observations by `time_h`, not by assuming the
returned row count equals the requested count. Values at bolus times are post-dose.
The builder uses 801 uniform samples; `Scenario()` defaults to 481. An imported
scenario preserves its `samples` value. All grids can gain extra event rows.

| CSV columns | Units and meaning |
| --- | --- |
| `time_h` | Hours from simulation zero |
| `central_mg_l`, `peripheral_1_mg_l`, `peripheral_2_mg_l` | Compartment concentrations; peripheral columns exist only when modeled |
| `effect_site_mg_l` | Virtual effect-site concentration; calculated even when plasma drives PD |
| `effect` | Direct response or turnover response, in user-defined response units |
| `depot_mg`, `central_mg`, `peripheral_1_mg`, `peripheral_2_mg` | Raw physical-compartment amount states |
| `eliminated_mg` | Cumulative removal from the central compartment |
| `auc_mg_h_l` | Cumulative central concentration integral in mg·h/L |
| `administered_mg` | Cumulative delivered dose, including only the delivered portion of infusions |
| `pending_lag_mg`, `unavailable_mg` | Oral amount awaiting release and amount excluded by F |
| `mass_balance_error_mg` | Accounted minus administered amount |

## Interpretation and current limitations

- Concentration plots break lines at IV bolus events rather than drawing ramps
  across jumps. These gaps are a display convention, not missing simulated data;
  the event row remains post-dose. They do not provide a separate pre-dose sample.
  Dotted vertical lines mark administration times, not delayed absorption starts.
- Log plots omit zero concentrations. A missing point does not establish a lower
  quantification limit or an observed concentration.
- Input validation establishes admissible model fields, not physiologically
  plausible parameters. The generated schema and a provenance label do not certify
  a published drug model. Literature mode only requires a nonempty references list;
  source authenticity and applicability need human review.
- Mass conservation does not by itself establish accurate concentration or effect
  curves. See [VALIDATION.md](VALIDATION.md) for the checked cases and remaining gaps.

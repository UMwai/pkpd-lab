# Lab builder

The v0.2 app opens in **Lab builder**. A lab contains independent subjects
(“bodies”); each subject owns its compartments, kinetic processes, parameters,
custom equations, and dose history. All subjects use the lab's time horizon and
base sampling grid. The original **PK/PD simulator** remains available from the
sidebar for its predefined PK/PD models, lag, infusions, and virtual populations.

## Create a lab and bodies

1. Choose **Create lab** and give the experiment a name, or **Open example lab**
   to start with two synthetic bodies having different clearances.
2. Under **Bodies & compartments**, expand **Add a body**. Choose a 1-, 2-, or
   3-compartment PK starting point, an empty equation system, or the higher-order
   mathematics example. Templates are editable starting points, not fitted drugs.
3. Select **Body to edit**. The diagram shows its physical compartment network.
   Edit names, symbols, volumes, and initial amounts, then **Apply body changes**.
   PK templates also include an absorption depot, excluded from their named PK
   compartment count. The lab's total compartment count includes that depot.
4. Add **Kinetic processes**, choosing source, destination (or Eliminate), order,
   and coefficient. Apply these before moving on. Remove referring processes
   and dose records before deleting a compartment; dangling links are rejected.
5. Set **Pulse dose schedule**. Dose a depot to model absorption or the central
   compartment to model an IV bolus. Dose amounts are exactly what enters the
   selected compartment: no implicit F, lag, first-pass correction, or infusion.
6. Use **Equations** to add parameters and explicit algebraic/differential
   relationships. Press each form's Apply button to include edits in the lab.

Body symbols are local to that body. Identical symbols in two bodies do not link
them. Duplicate a body to vary its parameters; bodies do not exchange drug.
The editor supports up to 12 bodies and 12 compartments per body. A compartment
is a mathematical distribution space, not an anatomical organ by default.

## Two distinct meanings of order

**Kinetic order** controls a physical process rate:

```text
requested rate = k * C_source^n     [mg/h]
C_source = amount_source / volume_source
```

| Kinetic order n | Requested rate | Coefficient units |
| --- | --- | --- |
| 0 | k | mg/h |
| 1 | k × C | L/h |
| 2 | k × C² | L²/(mg·h) |
| 3 | k × C³ | L³/(mg²·h) |

The solver subtracts the same rate from the source that it adds to the target;
an Eliminate process adds it to the elimination ledger. Multiple outgoing
processes add. Bidirectional exchange is two directed processes. Volume is fixed.
For first-order absorption specified as ka in 1/h, enter `ka * depot_volume_l`
as the process coefficient in L/h. For the 1 L template depot, ka=1.2/h therefore
corresponds to a coefficient of 1.2 L/h.

**Derivative order** specifies a custom equation's left-hand side:

| Derivative order | Meaning | Required initial values |
| --- | --- | --- |
| 0 | x = f(t, variables, parameters) | None; x is calculated |
| 1 | dx/dt = f(...) | x(0) |
| 2 | d²x/dt² = f(...) | x(0), x′(0) |
| 3 | d³x/dt³ = f(...) | x(0), x′(0), x″(0) |

A zero-order kinetic process still contributes to a first-order amount ODE.
It is not an order-zero algebraic equation. General implicit algebraic/DAE
systems are not supported: algebraic definitions must have an acyclic dependency
graph, and higher derivatives must be isolated on the left-hand side.

## Writing custom equations

Enter only the right-hand expression; choose the variable and derivative order
in their separate columns. Each physical compartment supplies `symbol` (amount,
mg) and `symbol_C` (concentration, mg/L). `t` is simulation time in hours.
Higher-order variable `x` exposes `x_d1` and, for third order, `x_d2`.

Examples:

| Variable/order/unit | Right-hand expression | Parameter definitions |
| --- | --- | --- |
| effect / 0 / response | `emax * central_C / (ec50 + central_C)` | emax: response; ec50: mg/L |
| x / 1 / response | `production - loss * x` | production: response/h; loss: 1/h |
| x / 2 / response | `-omega2 * x - damping * x_d1` | omega2: 1/h²; damping: 1/h |
| x / 3 / response | `jerk` | jerk: response/h³ |

In input fields, write squared/cubed units as `1/h^2`, `response/h^3`, etc.
Allowed base units are `mg`, `L`, `h`, `response`, and dimensionless `1`, combined
with `*`, `/`, parentheses, and integer powers. There is no automatic unit
conversion. An initial first derivative has units variable/h; a second derivative
has units variable/h². The API requires exactly n initial values for order n.
The UI uses the first n initial-condition columns and ignores the unused columns.

Expressions support numbers, declared symbols, `+ - * / ^` (or `**`), parentheses,
and `exp`, `log`, `sin`, `cos`. Function arguments must be dimensionless. Powers
must be integer constants from −8 through 8. Numeric literals are dimensionless,
except that an entire right-hand side of literal `0` is accepted for any units.
Give dimensional constants named parameters. Attribute access, subscripting,
imports, arbitrary function calls, and executable Python are rejected by the
arithmetic interpreter. Expressions are limited to 512 characters / 100 AST nodes.

Custom variables may depend on compartment amounts and concentrations, but do
not alter physical compartment fluxes or contribute to the mass ledger—even if
their chosen unit is mg. Negative custom states can be meaningful mathematically;
they are not automatically clipped. These checks establish structural and
dimensional consistency, not physiological plausibility.

## Generate and run

**Generate model** resolves references, checks equation units, orders algebraic
dependencies, and expands higher-order equations into first-order states. Inspect
the displayed equations, initial conditions, and dose events or download the
generated-model JSON. This artifact is a model description, not executable Python.

**Run simulation** then solves each subject independently. Only variables with
the selected units appear in **Variables to compare**. Plots and tables include
initial conditions, post-dose observations, and any inserted depletion or
reactivation boundaries. A requested base sample count is therefore not a
promise of the exact output row count. Changes to the lab invalidate the generated
model and hide old results until regeneration and a new run.

### Numerical and mass conventions

The lab engine uses SciPy DOP853 with rtol=1e-8 and atol=1e-10. Second- and
third-order equations are reduced to first-order state chains. For example,
`x'''=f` becomes `x'=x_d1`, `x_d1'=x_d2`, `x_d2'=f`. See the
[SciPy solver contract](https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html).
The legacy PK/PD simulator continues to use its documented LSODA engine.

For each subject:

```text
sum(physical compartment amounts) + eliminated
    = sum(initial physical amounts) + cumulative pulse doses
```

The simulator checks raw amount states, with a mass-residual tolerance of
`1e-6 * max(1, initial + total dosed mg)` and a negative-amount threshold of
`-1e-7 * max(1, initial + total dosed mg)`. Output physical amounts/concentrations
clip only smaller negative roundoff; the mass residual is computed beforehand.
These checks do not prove trajectory accuracy by themselves.

Zero-order demand stops exhausting a source at zero. At an empty source, outgoing
rates share any incoming drug in proportion to requested outgoing rates; they
cannot exceed the available incoming flow. This supports absorption into a body
with zero-order elimination. If inflow exceeds total demand, the source refills.
The solver restarts at depletion and reactivates the unconstrained source after
it accumulates `1e-9 * max(1, subject initial + total dosed mg)` to avoid repeated
events at exactly zero. This boundary convention is an approximation at that
small amount scale. Cycles between zero-order source compartments are rejected;
ordinary positive-order distribution cycles remain supported.

Each subject has a 15-second / 100,000-RHS-evaluation limit and at most 2,000
boundary restarts per dose interval. Failure, divergence, domain errors, and
conservation violations are reported explicitly; no fabricated result is returned.
The engine is not a general stiff DAE or arbitrary executable-code solver.

## Save and reproduce

**Save lab** writes JSON atomically to `~/.local/share/pkpd-lab/labs/<lab-id>.json`.
Set `PKPD_LAB_DATA_DIR` to use a different local folder. These files are not
committed to the repository. Saved labs survive process/browser restarts; ordinary
unsaved form edits and unsaved session state do not. Apply form edits before saving.
Opening another lab saves the current applied draft first. Saving an existing lab
replaces that lab ID's file; file version history is not currently provided.

**Export lab JSON** / **Import lab JSON** transport editable labs. This is a
separate `kind: lab`, `lab_schema_version: 1` format, not a replacement for the
legacy scenario format. Imports are limited to 2 MB; invalid fields, dangling
links, and IDs that could escape the storage folder are rejected. Draft equations
can be saved before generation; a saved draft is not necessarily runnable.

**Download complete run** produces a ZIP containing `lab.json`, `manifest.json`,
and one CSV per subject. The manifest records the resolved equations, units,
initial conditions, doses, lab serialization hash, output CSV hashes, Python and
platform, package versions, and solver tolerances. The hash identifies serialized
configuration, not scientific equivalence or authenticity. Archive the Git commit
and `uv.lock` separately; these are not embedded. Population fitting and
parameter-estimation uncertainty are not provided by this workflow.

Command-line equivalents:

```bash
uv run pkpd-lab generate examples/lab_clearance.json --output outputs/lab-model.json
uv run pkpd-lab run examples/lab_clearance.json --output outputs/lab-run.zip
uv run pkpd-lab run examples/lab_higher_order.json --output outputs/higher-order.zip
```

The lab CLI requires `.json` for generate and `.zip` for run, and refuses to
overwrite an existing output. Choose a fresh output name when repeating a command.

## Implemented boundaries

- Lab physical kinetics are concentration power laws with fixed coefficients and
  volumes. Custom response equations do not feed back into those coefficients.
- Lab dosing currently supports pulses. Use the original PK/PD simulator for
  finite infusions, fixed oral lag/F, and built-in Michaelis–Menten elimination.
- There is no automatic physiology derived from subject names or notes, no
  patient-specific calibration, no parameter fitting, and no clinical validation.
- Explicit examples and analytical tests cover selected cases; large/stiff
  networks and arbitrary custom equations require their own numerical validation.

The lab structure schema is [lab.schema.json](lab.schema.json). Python validators
and generation enforce additional cross-field, dependency, and dimensional rules.

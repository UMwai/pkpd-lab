# PK/PD Lab

This is a research simulator. Keep the numerical library independent of the UI.
Use hours, mg, L, mg/L, and L/h explicitly; never silently convert units.
Compartment counts include central and peripheral PK compartments, excluding
absorption depots and the virtual effect site. Synthetic examples must stay labeled.

Before changing equations or dose-event handling, read docs/MODELS.md. Preserve
mass balance, exact event boundaries, and right-continuous bolus observations.
Validate against independent analytical solutions or matrix exponentials, including
repeated doses and overlapping infusions. Never hide solver failures or fabricate
clinical validation. Cite drug-specific parameter sources and population/formulation
context before adding a named drug. Do not add patient records to this repository.

Required checks: `uv run ruff check .`, `uv run ruff format --check .`, and
`uv run pytest`. Keep `uv.lock` committed; CI uses `uv sync --locked`.

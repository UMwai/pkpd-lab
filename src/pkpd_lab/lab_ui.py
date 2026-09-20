"""Local-first lab editor and explicit generate/run workflow."""

import json
from uuid import uuid4

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .lab_engine import export_run, generate_lab, lab_hash, simulate_lab
from .lab_models import Compartment, Equation, Lab, Subject
from .lab_store import lab_directory, save_lab, saved_labs
from .lab_templates import example_lab, new_subject
from .presentation import PALETTE, chart


def _activate(lab, *, saved=False):
    st.session_state["active_lab"] = lab.model_dump(mode="json")
    st.session_state["lab_saved_hash"] = lab_hash(lab) if saved else None
    st.session_state.pop("lab_generated", None)
    st.session_state.pop("lab_run", None)
    st.rerun()


def _update(lab, **changes):
    updated = Lab.model_validate(lab.model_dump() | changes)
    st.session_state["active_lab"] = updated.model_dump(mode="json")
    st.rerun()


def _replace_subject(lab, subject):
    _update(lab, subjects=tuple(subject if s.id == subject.id else s for s in lab.subjects))


def _table(items, fields):
    return pd.DataFrame([x.model_dump() for x in items], columns=fields)


def _rows(frame):
    # Ignore only completely blank new rows. Partial records must pass validation.
    return frame.dropna(how="all").where(frame.notna(), None).to_dict("records")


def _subject_editor(lab, subject):
    if subject.compartments:
        nodes = {c.symbol: f"c{i}" for i, c in enumerate(subject.compartments)}
        dot = [
            'digraph Model { rankdir=LR; bgcolor="transparent"; '
            'node [shape=box style="rounded,filled" fillcolor="#edf8f7" '
            'color="#b8ddda" fontname="sans-serif" fontsize=11]; '
            'edge [color="#708196" fontname="sans-serif" fontsize=10];'
        ]
        for c in subject.compartments:
            label = json.dumps(f"{c.name}\n{c.symbol} · {c.volume_l:g} L", ensure_ascii=False)
            dot.append(f"{nodes[c.symbol]} [label={label}];")
        if any(p.target is None for p in subject.processes):
            dot.append('out [label="Eliminated" fillcolor="#f4f7fa"];')
        for p in subject.processes:
            target = nodes[p.target] if p.target else "out"
            label = json.dumps(
                f"{p.name}\norder {p.kinetic_order} · {p.coefficient:g} {p.coefficient_unit}",
                ensure_ascii=False,
            )
            dot.append(f"{nodes[p.source]} -> {target} [label={label}];")
        st.graphviz_chart("\n".join([*dot, "}"]))
    with st.form(f"body-{subject.id}"):
        st.subheader("Compartments")
        a, b = st.columns([1, 2])
        name = a.text_input("Body name", subject.name)
        notes = b.text_input("Body notes", subject.notes)
        st.caption(
            "Symbols name drug amounts in mg. Each symbol_C exposes concentration in mg/L. "
            "Apply new compartments before connecting them below."
        )
        edited = st.data_editor(
            _table(subject.compartments, ["symbol", "name", "volume_l", "initial_mg"]),
            num_rows="dynamic",
            width="stretch",
            key=f"compartments-{subject.id}",
            column_config={
                "symbol": st.column_config.TextColumn("Symbol", required=True),
                "name": "Label",
                "volume_l": st.column_config.NumberColumn("Volume (L)", min_value=0.001),
                "initial_mg": st.column_config.NumberColumn("Initial amount (mg)", min_value=0),
            },
        )
        if st.form_submit_button("Apply body changes"):
            try:
                new = Subject.model_validate(
                    subject.model_dump()
                    | {
                        "name": name,
                        "notes": notes,
                        "compartments": [Compartment.model_validate(row) for row in _rows(edited)],
                    }
                )
                _replace_subject(lab, new)
            except ValueError as exc:
                st.error(str(exc))
    symbols = [c.symbol for c in subject.compartments]
    with st.expander("Kinetic processes", expanded=True), st.form(f"processes-{subject.id}"):
        st.caption(
            "Rate = coefficient × source concentration^order, in mg/h. "
            "Transfers conserve mass; Eliminate removes drug from the body."
        )
        processes = _table(
            subject.processes, ["name", "source", "target", "kinetic_order", "coefficient"]
        )
        processes["target"] = processes.target.fillna("Eliminate")
        processes = st.data_editor(
            processes,
            num_rows="dynamic",
            width="stretch",
            key=f"process-table-{subject.id}",
            column_config={
                "source": st.column_config.SelectboxColumn("From", options=symbols, required=True),
                "target": st.column_config.SelectboxColumn(
                    "To", options=["Eliminate", *symbols], required=True
                ),
                "kinetic_order": st.column_config.SelectboxColumn(
                    "Kinetic order", options=[0, 1, 2, 3], required=True
                ),
                "coefficient": st.column_config.NumberColumn("Coefficient", min_value=0),
                "name": "Process",
            },
        )
        st.caption(
            "Coefficient units: order 0 = mg/h · order 1 = L/h · order 2 = L²/(mg·h) · "
            "order 3 = L³/(mg²·h). At depletion, outgoing rates are limited to incoming drug. "
            "Cycles between zero-order sources are not supported."
        )
        if st.form_submit_button("Apply kinetic processes"):
            try:
                rows = _rows(processes)
                for row in rows:
                    if row["target"] == "Eliminate":
                        row["target"] = None
                _replace_subject(
                    lab, Subject.model_validate(subject.model_dump() | {"processes": rows})
                )
            except ValueError as exc:
                st.error(str(exc))
    with st.expander("Pulse dose schedule"), st.form(f"doses-{subject.id}"):
        st.caption(
            "Target gut/depot for modeled absorption, or central for an IV bolus. "
            "Each dose is an instantaneous addition; no automatic bioavailability adjustment."
        )
        doses = st.data_editor(
            _table(subject.doses, ["time_h", "target", "amount_mg"]),
            num_rows="dynamic",
            width="stretch",
            key=f"dose-table-{subject.id}",
            column_config={
                "target": st.column_config.SelectboxColumn(options=symbols, required=True),
                "time_h": st.column_config.NumberColumn("Time (h)", min_value=0),
                "amount_mg": st.column_config.NumberColumn("Amount (mg)", min_value=0.001),
            },
        )
        if st.form_submit_button("Apply doses"):
            try:
                _replace_subject(
                    lab, Subject.model_validate(subject.model_dump() | {"doses": _rows(doses)})
                )
            except ValueError as exc:
                st.error(str(exc))


def _equation_editor(lab, subject):
    st.subheader("Custom equations")
    st.caption(f"Selected body: {subject.name}")
    st.write(
        "Order 0 defines an algebraic value. Orders 1–3 define time derivatives. "
        "The generator checks units, required initial conditions, and symbol references."
    )
    st.caption(
        "Use t (hours), compartment amounts (e.g. central), concentrations (central_C), "
        "parameters, other equation variables, and x_d1 / x_d2 for derivatives of x."
    )
    with st.form(f"parameters-{subject.id}"):
        st.markdown("**Named parameters**")
        parameters = st.data_editor(
            _table(subject.parameters, ["symbol", "value", "unit"]),
            num_rows="dynamic",
            width="stretch",
            key=f"params-table-{subject.id}",
        )
        st.caption(
            "Base units: mg, L, h, response, or 1. Combine with * / ^, e.g. response/h² "
            "is entered as response/h^2. Numeric literals are dimensionless."
        )
        if st.form_submit_button("Apply parameters"):
            try:
                _replace_subject(
                    lab,
                    Subject.model_validate(
                        subject.model_dump() | {"parameters": _rows(parameters)}
                    ),
                )
            except ValueError as exc:
                st.error(str(exc))
    equation_rows = [
        {
            "symbol": e.symbol,
            "derivative_order": e.derivative_order,
            "rhs": e.rhs,
            "unit": e.unit,
            **{f"initial_{i}": e.initial[i] if len(e.initial) > i else 0.0 for i in range(3)},
        }
        for e in subject.equations
    ]
    with st.form(f"equations-{subject.id}"):
        edited = st.data_editor(
            pd.DataFrame(
                equation_rows,
                columns=[
                    "symbol",
                    "derivative_order",
                    "rhs",
                    "unit",
                    "initial_0",
                    "initial_1",
                    "initial_2",
                ],
            ),
            num_rows="dynamic",
            width="stretch",
            key=f"equations-table-{subject.id}",
            column_config={
                "symbol": "Variable",
                "derivative_order": st.column_config.SelectboxColumn(
                    "Derivative order", options=[0, 1, 2, 3], required=True
                ),
                "rhs": st.column_config.TextColumn("Right-hand side", width="large"),
                "unit": "Variable units",
                "initial_0": "x(0)",
                "initial_1": "x′(0)",
                "initial_2": "x″(0)",
            },
        )
        st.caption(
            "Order 0 uses no initial conditions; order 1 uses x(0); order 2 also uses x′(0); "
            "order 3 uses all three. Derivative initial values have units x/h and x/h². "
            "Custom variables do not add to physical drug mass."
        )
        if st.form_submit_button("Apply equations"):
            try:
                equations = []
                for row in _rows(edited):
                    order = row["derivative_order"]
                    if order not in (0, 1, 2, 3):
                        raise ValueError("Choose an equation order from 0 through 3")
                    equations.append(
                        Equation(
                            symbol=row["symbol"],
                            derivative_order=order,
                            rhs=row["rhs"],
                            unit=row["unit"],
                            initial=tuple(row[f"initial_{i}"] for i in range(int(order))),
                        )
                    )
                _replace_subject(
                    lab, Subject.model_validate(subject.model_dump() | {"equations": equations})
                )
            except ValueError as exc:
                st.error(str(exc))
    with st.expander("Equation examples"):
        st.code(
            "effect = emax * central_C / (ec50 + central_C)  # order 0\n"
            "dx/dt = production - loss * x                  # order 1\n"
            "d²x/dt² = -omega2 * x                          # order 2\n"
            "d³x/dt³ = jerk                                # order 3",
            language="text",
        )
        st.caption(
            "Enter only the right-hand expression in the table, with matching parameter units. "
            "Supported functions: exp, log, sin, cos (dimensionless arguments). "
            "Implicit algebraic cycles and executable code are rejected."
        )


def _run_panel(lab):
    st.subheader("Generate, inspect, then run")
    st.write(
        "Assemble each body's compartments and equations into a numerical model. "
        "Bodies run independently on the same time horizon."
    )
    signature = lab_hash(lab)
    if st.button("Generate model", type="primary"):
        try:
            st.session_state["lab_generated"] = generate_lab(lab)
            st.session_state.pop("lab_run", None)
        except ValueError as exc:
            st.session_state.pop("lab_generated", None)
            st.error(str(exc))
    generated = st.session_state.get("lab_generated")
    if generated is None or generated["lab_sha256"] != signature:
        st.info("Generate the current lab to check its equations and unlock simulation.")
        return
    st.success(f"Model generated · {len(lab.subjects)} bodies · references and units checked")
    for item in generated["subjects"]:
        with st.expander(f"{item['name']} — assembled equations"):
            st.code("\n".join(item["equations"]), language="text")
            st.json(
                {"initial_state": item["initial_state"], "dose_events": item["dose_events"]},
                expanded=False,
            )
    st.download_button(
        "Download generated model",
        json.dumps(generated, indent=2),
        "generated-model.json",
        "application/json",
    )
    if st.button("Run simulation", type="primary"):
        try:
            with st.spinner("Solving the lab…"):
                results = simulate_lab(lab)
            st.session_state["lab_run"] = (signature, results)
        except ValueError as exc:
            st.session_state.pop("lab_run", None)
            st.error(f"Simulation could not be completed: {exc}")
    run = st.session_state.get("lab_run")
    if run is None or run[0] != signature:
        return
    results = run[1]
    st.subheader("Lab results")
    units = sorted(
        {
            unit
            for item in generated["subjects"]
            for symbol, unit in item["units"].items()
            if symbol != "time_h"
        }
    )
    if units:
        unit = st.selectbox(
            "Plot units", units, index=units.index("mg/L") if "mg/L" in units else 0
        )
        symbols = sorted(
            {
                symbol
                for item in generated["subjects"]
                for symbol, u in item["units"].items()
                if u == unit and symbol != "time_h"
            }
        )
        chosen = st.multiselect(
            "Variables to compare",
            symbols,
            default=["central_C"] if "central_C" in symbols else symbols[:1],
        )
        figure = None
        trace_count = 0
        for subject, compiled in zip(lab.subjects, generated["subjects"], strict=True):
            columns = {
                s: f"{subject.name} · {s}" for s in chosen if compiled["units"].get(s) == unit
            }
            if not columns:
                continue
            item = chart(
                results[subject.id], columns, unit, breaks=[d.time_h for d in subject.doses]
            )
            if figure is None:
                figure = go.Figure(layout=item.layout)
            for trace in item.data:
                color = PALETTE[trace_count % len(PALETTE)]
                trace.line.color = trace.marker.color = color
                figure.add_trace(trace)
                trace_count += 1
        if figure is not None:
            st.plotly_chart(figure, width="stretch")
    residual = max(float(frame.mass_balance_error_mg.abs().max()) for frame in results.values())
    st.caption(
        f"Maximum physical mass residual: {residual:.2e} mg. "
        "Custom response variables are not part of the physical mass ledger."
    )
    st.download_button(
        "Download complete run", export_run(lab, results), "lab-run.zip", "application/zip"
    )
    for subject in lab.subjects:
        with st.expander(f"{subject.name} — numerical output"):
            st.dataframe(results[subject.id], hide_index=True, width="stretch")


def render_lab():
    with st.sidebar:
        st.markdown(
            '<div class="lab-wordmark"><span class="lab-mark">◒</span> PK/PD Lab</div>'
            '<div class="lab-owner">UMWAI / MODEL BUILDER</div>',
            unsafe_allow_html=True,
        )
    st.markdown(
        '<div class="page-kicker">MODEL DESIGN / GENERATION / SIMULATION</div>',
        unsafe_allow_html=True,
    )
    current = st.session_state.get("active_lab")
    labs, errors = saved_labs()
    if current is None:
        st.title("Create your research lab")
        st.write(
            "Build bodies, connect their compartments, and define the equations that drive them."
        )
        a, b, c = st.columns(3)
        for col, title, detail in (
            (a, "01 · Create bodies", "Each subject has its own compartments and parameters."),
            (b, "02 · Define the model", "Add kinetic processes and custom equations, orders 0–3."),
            (c, "03 · Generate & run", "Check units, inspect equations, then compare simulations."),
        ):
            with col, st.container(border=True):
                st.subheader(title)
                st.write(detail)
        with st.form("create-lab"):
            name = st.text_input("New lab name", "My research lab")
            description = st.text_input("Lab description", "Synthetic research experiment")
            if st.form_submit_button("Create lab", type="primary"):
                try:
                    _activate(Lab(name=name, description=description))
                except ValueError as exc:
                    st.error(str(exc))
        if st.button("Open example lab"):
            _activate(example_lab())
    else:
        lab = Lab.model_validate(current)
        st.title(lab.name)
        st.caption(
            f"{len(lab.subjects)} bodies · "
            f"{sum(len(s.compartments) for s in lab.subjects)} compartments · "
            f"{sum(len(s.equations) for s in lab.subjects)} custom equations · Synthetic research"
        )
        a, b, c = st.columns(3)
        if a.button("Save lab", type="primary", width="stretch"):
            save_lab(lab)
            st.session_state["lab_saved_hash"] = lab_hash(lab)
            st.success("Lab saved locally")
        b.download_button(
            "Export lab JSON",
            lab.model_dump_json(indent=2),
            "lab.json",
            "application/json",
            width="stretch",
        )
        if c.button("Save & create another lab", width="stretch"):
            save_lab(lab)
            st.session_state.pop("active_lab", None)
            st.rerun()
        st.caption(
            "Saved locally"
            if st.session_state.get("lab_saved_hash") == lab_hash(lab)
            else "Unsaved changes · Save locally or export JSON to keep this lab"
        )
        with st.expander("Lab settings"):
            with st.form("lab-settings"):
                name = st.text_input("Lab name", lab.name)
                description = st.text_input("Lab description", lab.description)
                end = st.number_input("Lab horizon (h)", 0.01, 10000.0, float(lab.end_h))
                samples = st.number_input("Output samples", 2, 10001, lab.samples)
                if st.form_submit_button("Apply lab settings"):
                    try:
                        _update(lab, name=name, description=description, end_h=end, samples=samples)
                    except ValueError as exc:
                        st.error(str(exc))
        bodies, equations, run = st.tabs(["Bodies & compartments", "Equations", "Generate & run"])
        with bodies:
            with st.expander("Add a body", expanded=not lab.subjects), st.form("add-body"):
                name = st.text_input("New body name", f"Body {len(lab.subjects) + 1}")
                template = st.selectbox(
                    "Starting model",
                    [
                        "1 compartment",
                        "2 compartments",
                        "3 compartments",
                        "Empty equation system",
                        "Higher-order example",
                    ],
                    index=1,
                )
                st.caption(
                    "PK templates include a separate absorption depot; "
                    "it is excluded from the named PK compartment count."
                )
                if st.form_submit_button("Add body", type="primary"):
                    try:
                        body = new_subject(name, template)
                        # Keep short-horizon labs valid when adding a starter dosing history.
                        body = Subject.model_validate(
                            body.model_dump()
                            | {"doses": [d for d in body.doses if d.time_h <= lab.end_h]}
                        )
                        _update(lab, subjects=(*lab.subjects, body))
                    except ValueError as exc:
                        st.error(str(exc))
            if lab.subjects:
                with st.sidebar:
                    st.subheader("Bodies in this lab")
                    index = st.selectbox(
                        "Body to edit",
                        range(len(lab.subjects)),
                        format_func=lambda i: lab.subjects[i].name,
                    )
                    st.caption(
                        "This selection applies to compartments and custom equations. "
                        "Generate & run includes every body in the lab."
                    )
                subject = lab.subjects[index]
                _subject_editor(lab, subject)
                if st.button("Duplicate selected body", disabled=len(lab.subjects) >= 12):
                    duplicate = Subject.model_validate(
                        subject.model_dump()
                        | {"id": uuid4().hex, "name": subject.name[:89] + " (copy)"}
                    )
                    _update(lab, subjects=(*lab.subjects, duplicate))
                with st.expander("Remove selected body"):
                    confirmed = st.checkbox(f"Remove {subject.name} and its model from this lab")
                    if st.button("Remove body", disabled=not confirmed):
                        _update(lab, subjects=tuple(s for s in lab.subjects if s.id != subject.id))
        with equations:
            if lab.subjects:
                _equation_editor(lab, subject)
            else:
                st.info("Add a body before defining its equations.")
        with run:
            _run_panel(lab)
    st.divider()
    with st.expander("Open saved lab / import lab JSON", expanded=current is None and bool(labs)):
        if labs:
            index = st.selectbox(
                "Saved labs",
                range(len(labs)),
                format_func=lambda i: f"{labs[i].name} · {labs[i].id[:8]}",
            )
            if st.button("Save current & open selected lab" if current else "Open saved lab"):
                selected = labs[index]
                if current:
                    active = Lab.model_validate(current)
                    save_lab(active)
                    if active.id == selected.id:
                        selected = active
                _activate(selected, saved=True)
        uploaded = st.file_uploader("Import lab JSON", type=["json"])
        if uploaded and st.button("Save current & import" if current else "Import lab"):
            try:
                if uploaded.size > 2_000_000:
                    raise ValueError("Lab imports are limited to 2 MB")
                incoming = Lab.model_validate_json(uploaded.getvalue())
                if current:
                    save_lab(Lab.model_validate(current))
                _activate(incoming)
            except ValueError as exc:
                st.error(str(exc))
        for error in errors:
            st.warning(f"Could not load saved lab: {error}")
        st.caption(f"Local storage: {lab_directory()}. JSON only; no cloud account required.")
    st.caption(
        "Research models, not patient records or clinical dosing advice. "
        "Use PK/PD simulator in the sidebar for the original scenario workbench."
    )

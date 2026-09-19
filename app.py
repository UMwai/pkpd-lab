"""Run with: uv run streamlit run app.py"""

import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pydantic import ValidationError

from pkpd_lab import Dose, PDParameters, PKParameters, Scenario, repeated_doses, simulate
from pkpd_lab.experiments import population, sensitivity

st.set_page_config(page_title="PK/PD Lab · UMWai", page_icon="◒", layout="wide")
st.markdown(
    """
<style>
 .block-container {max-width: 1440px; padding-top: 2.2rem;}
 h1 {font-family: Georgia, serif; font-size: 3.8rem !important; letter-spacing: -.055em;}
 h2, h3 {font-family: Georgia, serif; letter-spacing: -.025em;}
 .eyebrow {font-family: monospace; text-transform: uppercase; letter-spacing: .2em;
            color: #087f73; font-size: .76rem; margin-bottom: .5rem;}
 .intro {max-width: 720px; color: #52645e; font-size: 1.12rem; line-height: 1.6;}
 [data-testid="stMetric"] {border-top: 2px solid #afbbb0; padding-top: .8rem;}
 [data-testid="stMetricLabel"] {font-family: monospace; font-size: .75rem;}
 [data-testid="stSidebar"] {border-right: 1px solid #d3d9d0;}
 .stButton button {border-radius: 3px;}
</style>
<div class="eyebrow">UMWai / Research instruments / 001</div>
""",
    unsafe_allow_html=True,
)
st.title("Follow the dose.")
st.markdown(
    '<p class="intro">Explore how a dose moves through the body, how exposure changes '
    "over time, and how an effect emerges. A compartmental PK/PD workbench.</p>",
    unsafe_allow_html=True,
)
st.caption("Synthetic parameters · Research and education · Not validated for clinical dosing")

with st.sidebar:
    st.header("Experiment setup")
    source = st.radio("Scenario source", ["Build a scenario", "Import JSON"])
    uploaded = None
    if source == "Import JSON":
        uploaded = st.file_uploader("Version 1 scenario", type=["json"])
        st.caption(
            "Import restores the full scenario, including provenance and custom dose events."
        )
    compartments = st.select_slider("PK compartments", options=[1, 2, 3], value=2)
    route_label = st.selectbox("Administration", ["Oral", "IV bolus", "IV infusion"])
    route = {"Oral": "oral", "IV bolus": "iv_bolus", "IV infusion": "iv_infusion"}[route_label]
    amount = st.number_input("Dose (mg)", 0.1, 10000.0, 100.0, step=10.0)
    count = st.number_input("Number of doses", 1, 100, 4)
    interval = st.number_input("Interval (h)", 0.1, 168.0, 12.0)
    duration = (
        st.number_input("Infusion duration (h)", 0.1, 48.0, 1.0) if route == "iv_infusion" else 0.0
    )
    default_end = max(48.0, (count - 1) * interval + max(duration, 12.0))
    horizon = st.number_input("Simulation horizon (h)", 1.0, 20000.0, default_end)
    with st.expander("Disposition", expanded=True):
        clearance = st.number_input("Clearance CL (L/h)", 0.0, 500.0, 4.0)
        vc = st.number_input("Central volume Vc (L)", 0.1, 5000.0, 20.0)
        vp, q = [], []
        for i in range(compartments - 1):
            vp.append(st.number_input(f"Peripheral V{i + 1} (L)", 0.1, 5000.0, 30.0 + i * 50))
            q.append(st.number_input(f"Distribution Q{i + 1} (L/h)", 0.0, 500.0, 6.0 / (i + 1)))
    with st.expander("Absorption & elimination"):
        ka = st.number_input("Absorption ka (1/h)", 0.001, 100.0, 1.2)
        f = st.slider("Oral bioavailability F", 0.0, 1.0, 0.8)
        lag = st.number_input("Oral absorption lag (h)", 0.0, 72.0, 0.0)
        nonlinear = st.checkbox("Add saturable elimination")
        vmax = st.number_input("Vmax (mg/h)", 0.0, 10000.0, 10.0) if nonlinear else 0.0
        km = st.number_input("Km (mg/L)", 0.001, 1000.0, 2.0) if nonlinear else 2.0
        st.caption(
            "Saturable elimination is added to CL. Set CL to zero for a pure saturable model."
        )
    with st.expander("Pharmacodynamics"):
        pd_kind = st.selectbox(
            "Response model", ["emax", "linear", "indirect_inhibition", "indirect_stimulation"]
        )
        driver = st.selectbox("Effect driver", ["effect_site", "plasma"])
        indirect = pd_kind.startswith("indirect")
        baseline = st.number_input(
            "Baseline response", 0.01 if indirect else 0.0, 10000.0, 100.0 if indirect else 0.0
        )
        if pd_kind == "indirect_inhibition":
            emax = st.slider("Maximum inhibition fraction", 0.0, 1.0, 0.8)
        else:
            emax = st.number_input(
                "Maximum effect change / stimulation",
                0.0 if indirect else -10000.0,
                10000.0,
                1.0 if indirect else 100.0,
            )
        ec50 = st.number_input("EC50 / IC50 (mg/L)", 0.001, 1000.0, 2.0)
        hill = st.number_input("Hill coefficient", 0.1, 10.0, 1.0)
        slope = st.number_input("Linear slope (response per mg/L)", -1000.0, 1000.0, 1.0)
        ke0 = st.number_input("Effect equilibration ke0 (1/h)", 0.001, 100.0, 0.5)
        kout = st.number_input("Response turnover kout (1/h)", 0.001, 100.0, 0.2)
    custom = st.checkbox("Edit individual dose events")

try:
    if source == "Import JSON":
        if uploaded is None:
            st.info("Choose a scenario JSON file to begin, or switch to Build a scenario.")
            st.stop()
        scenario = Scenario.model_validate_json(uploaded.getvalue())
        st.info(
            f"Imported: {scenario.name}. Sidebar model controls apply only in Build a scenario."
        )
    else:
        doses = repeated_doses(amount, interval, count, route=route, duration_h=duration)
        if custom:
            st.subheader("Dose event ledger")
            st.caption(
                "Edit times and amounts, remove missed doses, or mix routes. All times are hours."
            )
            edited = st.data_editor(
                pd.DataFrame([d.model_dump() for d in doses]),
                num_rows="dynamic",
                column_config={
                    "route": st.column_config.SelectboxColumn(
                        options=["oral", "iv_bolus", "iv_infusion"], required=True
                    )
                },
            )
            doses = tuple(Dose.model_validate(row) for row in edited.to_dict("records"))
        scenario = Scenario(
            name=f"Synthetic {compartments}-compartment {route_label.lower()} scenario",
            pk=PKParameters(
                clearance_l_h=clearance,
                central_volume_l=vc,
                peripheral_volumes_l=tuple(vp),
                intercompartmental_clearances_l_h=tuple(q),
                absorption_rate_h=ka,
                bioavailability=f,
                absorption_lag_h=lag,
                vmax_mg_h=vmax,
                km_mg_l=km,
            ),
            pd=PDParameters(
                model=pd_kind,
                driver=driver,
                baseline=baseline,
                maximum_effect=emax,
                ec50_mg_l=ec50,
                hill=hill,
                slope_per_mg_l=slope,
                effect_equilibration_h=ke0,
                turnover_rate_h=kout,
            ),
            doses=doses,
            end_h=horizon,
            samples=801,
        )
    result = simulate(scenario)
except (ValueError, ValidationError, RuntimeError) as exc:
    st.error(f"Please revise the scenario: {exc}")
    st.stop()

frame, summary = result.frame, result.summary()
cols = st.columns(4)
for col, label, value in zip(
    cols,
    ["SAMPLED CMAX · mg/L", "SAMPLED TMAX · h", "AUC 0–END · mg·h/L", "END CONCENTRATION · mg/L"],
    [
        summary["cmax_sampled_mg_l"],
        summary["tmax_sampled_h"],
        summary["auc_0_end_mg_h_l"],
        summary["concentration_end_mg_l"],
    ],
    strict=True,
):
    col.metric(label, f"{value:,.3f}")

PALETTE = ["#087f73", "#c46a36", "#587b9b", "#9d8548"]


def chart(data, columns, y_label, log=False):
    fig = go.Figure()
    for i, (column, name) in enumerate(columns.items()):
        # Do not replace zero concentrations with a made-up log-floor value.
        y = data[column].where(data[column] > 0) if log else data[column]
        fig.add_trace(
            go.Scatter(
                x=data.time_h,
                y=y,
                name=name,
                mode="lines",
                line={"color": PALETTE[i % len(PALETTE)], "width": 2.4},
            )
        )
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Georgia", "color": "#192d2a"},
        margin={"l": 12, "r": 12, "t": 25, "b": 20},
        height=400,
        xaxis_title="Time after first reference time (h)",
        yaxis_title=y_label,
        legend={"orientation": "h", "y": 1.14},
        hovermode="x unified",
    )
    fig.update_yaxes(type="log" if log else "linear", gridcolor="#dfe4db")
    return fig


trajectory, comparison, experiments, record = st.tabs(
    ["01 / Trajectories", "02 / Compare models", "03 / Variability", "04 / Experiment record"]
)
with trajectory:
    left, right = st.columns([1.5, 1])
    with left:
        st.subheader("Exposure over time")
        log = st.checkbox("Log concentration axis")
        columns = {"central_mg_l": "Central", "effect_site_mg_l": "Effect site"}
        for i in range(scenario.pk.compartments - 1):
            columns[f"peripheral_{i + 1}_mg_l"] = f"Peripheral {i + 1}"
        st.plotly_chart(chart(frame, columns, "Concentration (mg/L)", log), width="stretch")
    with right:
        st.subheader("Pharmacodynamic response")
        st.caption(
            f"{scenario.pd.model.replace('_', ' ').title()} · "
            f"{scenario.pd.driver.replace('_', ' ')} driver"
        )
        st.plotly_chart(
            chart(frame, {"effect": "Response"}, "Response (arbitrary units)"),
            width="stretch",
        )
    st.caption(
        "Cmax and Tmax depend on the output grid. AUC is integrated by the solver through the "
        "simulation horizon; it is not AUC to infinity. "
        "Peripheral compartments are abstract spaces."
    )
    with st.expander("Dose schedule & mass accounting"):
        st.dataframe(pd.DataFrame([d.model_dump() for d in scenario.doses]), hide_index=True)
        st.plotly_chart(
            chart(
                frame,
                {
                    "administered_mg": "Administered",
                    "eliminated_mg": "Eliminated",
                    "unavailable_mg": "Unavailable (1−F)",
                    "pending_lag_mg": "Waiting for absorption lag",
                },
                "Amount (mg)",
            ),
            width="stretch",
        )
        st.caption(
            "Maximum absolute mass balance residual: "
            f"{summary['max_abs_mass_balance_error_mg']:.2e} mg"
        )

with comparison:
    st.subheader("One dose history. Three distribution models.")
    st.write(
        "Keep central volume, clearance, absorption, and dose events fixed. Add peripheral "
        "distribution to explore how model structure changes the curve."
    )
    st.caption(
        "These are structural scenarios, not fitted competing models. Added peripheral values "
        "use V1=30 L, Q1=6 L/h; V2=80 L, Q2=3 L/h unless present in your scenario."
    )
    comparison_data = pd.DataFrame({"time_h": frame.time_h})
    comparison_rows = []
    for n in (1, 2, 3):
        p = scenario.pk.model_dump()
        p["peripheral_volumes_l"] = tuple(
            (list(scenario.pk.peripheral_volumes_l) + [30.0, 80.0])[: n - 1]
        )
        p["intercompartmental_clearances_l_h"] = tuple(
            (list(scenario.pk.intercompartmental_clearances_l_h) + [6.0, 3.0])[: n - 1]
        )
        # Preserve the defaults by peripheral index when only one peripheral exists.
        if n == 3 and scenario.pk.compartments == 2:
            p["peripheral_volumes_l"] = (scenario.pk.peripheral_volumes_l[0], 80.0)
            p["intercompartmental_clearances_l_h"] = (
                scenario.pk.intercompartmental_clearances_l_h[0],
                3.0,
            )
        candidate = Scenario.model_validate(scenario.model_dump() | {"pk": p})
        r = simulate(candidate)
        comparison_data[f"model_{n}"] = r.frame.central_mg_l
        comparison_rows.append({"PK compartments": n, **r.summary()})
    st.plotly_chart(
        chart(
            comparison_data,
            {f"model_{n}": f"{n} compartment" for n in (1, 2, 3)},
            "Central concentration (mg/L)",
        ),
        width="stretch",
    )
    st.dataframe(
        pd.DataFrame(comparison_rows).drop(columns="max_abs_mass_balance_error_mg"), hide_index=True
    )

with experiments:
    st.subheader("Explore assumptions, then measure their impact.")
    st.write(
        "Virtual subjects vary CL and central volume independently. Bands show the middle 90% "
        "of simulated concentrations at each time, conditional on your chosen variability."
    )
    c1, c2, c3, c4 = st.columns(4)
    subjects = c1.slider("Virtual subjects", 10, 200, 50, step=10)
    cl_cv = c2.slider("Clearance CV", 0.0, 1.0, 0.3)
    v_cv = c3.slider("Central volume CV", 0.0, 1.0, 0.3)
    seed = c4.number_input("Random seed", 0, 1000000, 42)
    population_key = (scenario.model_dump_json(), subjects, cl_cv, v_cv, seed)
    if st.button("Run virtual population", type="primary"):
        with st.spinner("Simulating virtual subjects…"):
            bands = population(
                scenario, subjects=subjects, clearance_cv=cl_cv, volume_cv=v_cv, seed=seed
            )
            st.session_state["population_result"] = (population_key, bands)
    stored_population = st.session_state.get("population_result")
    if stored_population is not None and stored_population[0] == population_key:
        bands = stored_population[1]
        fig = chart(
            bands,
            {"p05_mg_l": "5th percentile", "p50_mg_l": "Median", "p95_mg_l": "95th percentile"},
            "Central concentration (mg/L)",
        )
        st.plotly_chart(fig, width="stretch")
        st.download_button(
            "Download population bands", bands.to_csv(index=False), "population.csv", "text/csv"
        )
        experiment = {
            "scenario": scenario.model_dump(mode="json"),
            "subjects": subjects,
            "clearance_cv": cl_cv,
            "volume_cv": v_cv,
            "seed": seed,
            "distribution": "Independent lognormal CL and Vc; scenario values are medians",
        }
        st.download_button(
            "Download population assumptions",
            json.dumps(experiment, indent=2),
            "population-assumptions.json",
            "application/json",
        )
    st.caption(
        "These bands are not confidence intervals, a fitted population model, or evidence "
        "of clinical variability. No measurement noise or parameter uncertainty is included."
    )
    st.divider()
    parameter = st.selectbox(
        "Sensitivity parameter", ["clearance_l_h", "central_volume_l", "absorption_rate_h"]
    )
    sensitivity_key = (scenario.model_dump_json(), parameter)
    if st.button("Compare −20%, baseline, +20%"):
        try:
            st.session_state["sensitivity_result"] = (
                sensitivity_key,
                sensitivity(scenario, parameter),
            )
        except ValueError as exc:
            st.warning(str(exc))
    stored_sensitivity = st.session_state.get("sensitivity_result")
    if stored_sensitivity is not None and stored_sensitivity[0] == sensitivity_key:
        st.dataframe(stored_sensitivity[1], hide_index=True)

with record:
    st.subheader("An experiment you can reproduce.")
    st.write(
        f"Parameter provenance: **{scenario.provenance.kind}**. {scenario.provenance.description}"
    )
    st.caption(
        "Model validation is separate from source provenance. "
        "Every imported scenario remains research-only."
    )
    a, b = st.columns(2)
    a.download_button(
        "Download scenario JSON",
        scenario.model_dump_json(indent=2),
        "scenario.json",
        "application/json",
        width="stretch",
    )
    b.download_button(
        "Download trajectory CSV",
        frame.to_csv(index=False),
        "trajectory.csv",
        "text/csv",
        width="stretch",
    )
    st.json(scenario.model_dump(mode="json"), expanded=False)
    st.dataframe(frame, hide_index=True)
    st.markdown(
        "Model equations, assumptions, references, and the extension roadmap live in "
        "[the project documentation](https://github.com/UMwai/pkpd-lab/tree/main/docs)."
    )
st.divider()
st.caption("PK/PD LAB / 0.1 · Hours, milligrams, liters · Zero initial drug · Explicit dose events")

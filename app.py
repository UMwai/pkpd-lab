"""Run with: uv run streamlit run app.py"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from pkpd_lab import Dose, PDParameters, PKParameters, Scenario, repeated_doses, simulate
from pkpd_lab.experiments import population, sensitivity
from pkpd_lab.presentation import chart, model_diagram

st.set_page_config(page_title="PK/PD Lab · UMWai", page_icon="◒", layout="wide")
st.markdown(
    "<style>" + (Path(__file__).parent / "assets/workbench.css").read_text() + "</style>",
    unsafe_allow_html=True,
)
st.markdown('<div class="page-kicker">RESEARCH WORKBENCH</div>', unsafe_allow_html=True)
header, status = st.columns([4, 1], vertical_alignment="center")
with header:
    st.title("Simulation workspace")
    st.markdown(
        '<div class="page-subtitle">Explore exposure, distribution, '
        "and drug effects in one experiment.</div>",
        unsafe_allow_html=True,
    )
with status:
    st.markdown('<span class="status-tag">RESEARCH ONLY · v0.1</span>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown(
        '<div class="lab-wordmark"><span class="lab-mark">◒</span> PK/PD Lab</div>'
        '<div class="lab-owner">UMWAI / PHARMACOMETRICS</div>',
        unsafe_allow_html=True,
    )
    st.header("Experiment setup")
    source = st.radio("Scenario source", ["Build a scenario", "Import JSON"])
    uploaded = None
    if source == "Import JSON":
        uploaded = st.file_uploader("Version 1 scenario", type=["json"])
        st.caption(
            "Import restores the full scenario, including provenance and custom dose events."
        )
    if source == "Build a scenario":
        compartments = st.select_slider("PK compartments", options=[1, 2, 3], value=2)
        route_label = st.selectbox("Administration", ["Oral", "IV bolus", "IV infusion"])
        route = {"Oral": "oral", "IV bolus": "iv_bolus", "IV infusion": "iv_infusion"}[route_label]
        a, b = st.columns(2)
        amount = a.number_input("Dose (mg)", 0.1, 10000.0, 100.0, step=10.0)
        count = b.number_input("Number of doses", 1, 100, 4)
        interval = st.number_input("Interval (h)", 0.1, 168.0, 12.0)
        duration = (
            st.number_input("Infusion duration (h)", 0.1, 48.0, 1.0)
            if route == "iv_infusion"
            else 0.0
        )
        default_end = max(48.0, (count - 1) * interval + max(duration, 12.0))
        horizon = st.number_input("Simulation horizon (h)", 1.0, 20000.0, default_end)
        with st.expander("Distribution & clearance"):
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
            emax, ec50, hill, slope, ke0, kout = 100.0, 2.0, 1.0, 1.0, 0.5, 0.2
            if pd_kind == "indirect_inhibition":
                emax = st.slider("Maximum inhibition fraction", 0.0, 1.0, 0.8)
            elif pd_kind != "linear":
                emax = st.number_input(
                    "Maximum effect change / stimulation",
                    0.0 if indirect else -10000.0,
                    10000.0,
                    1.0 if indirect else 100.0,
                )
            if pd_kind != "linear":
                ec50 = st.number_input("EC50 / IC50 (mg/L)", 0.001, 1000.0, 2.0)
                hill = st.number_input("Hill coefficient", 0.1, 10.0, 1.0)
            else:
                slope = st.number_input("Linear slope (response per mg/L)", -1000.0, 1000.0, 1.0)
            if driver == "effect_site":
                ke0 = st.number_input("Effect equilibration ke0 (1/h)", 0.001, 100.0, 0.5)
            if indirect:
                kout = st.number_input("Response turnover kout (1/h)", 0.001, 100.0, 0.2)
        custom = st.checkbox("Edit individual dose events")

try:
    if source == "Import JSON":
        if uploaded is None:
            st.info("Choose a scenario JSON file to begin, or switch to Build a scenario.")
            st.stop()
        scenario = Scenario.model_validate_json(uploaded.getvalue())
        st.info(f"Imported: {scenario.name}. Parameters and dose history come from this file.")
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
st.caption(
    f"{scenario.pk.compartments}-compartment model · {len(scenario.doses)} dose events · "
    f"{scenario.end_h:g} h horizon · {scenario.provenance.kind.title()} parameters"
)
st.markdown(model_diagram(scenario), unsafe_allow_html=True)
bolus_times = tuple(d.time_h for d in scenario.doses if d.route == "iv_bolus")
dose_times = tuple(d.time_h for d in scenario.doses)
cols = st.columns(4)
for col, label, value in zip(
    cols,
    [
        "Sampled peak · mg/L",
        "Sampled peak time · h",
        "AUC 0–end · mg·h/L",
        "Final concentration · mg/L",
    ],
    [
        summary["cmax_sampled_mg_l"],
        summary["tmax_sampled_h"],
        summary["auc_0_end_mg_h_l"],
        summary["concentration_end_mg_l"],
    ],
    strict=True,
):
    col.metric(label, f"{value:,.3f}")

trajectory, comparison, experiments, record = st.tabs(
    ["Trajectories", "Compare models", "Variability", "Experiment record"]
)
with trajectory:
    with st.container(border=True):
        title, display = st.columns([3, 1], vertical_alignment="center")
        title.subheader("Concentration–time profile")
        log = display.toggle("Log concentration axis")
        columns = {"central_mg_l": "Central"}
        if scenario.pd.driver == "effect_site":
            columns["effect_site_mg_l"] = "Effect site"
        for i in range(scenario.pk.compartments - 1):
            columns[f"peripheral_{i + 1}_mg_l"] = f"Peripheral {i + 1}"
        st.plotly_chart(
            chart(
                frame,
                columns,
                "Concentration (mg/L)",
                log=log,
                breaks=bolus_times,
                dose_times=dose_times,
                height=365,
            ),
            width="stretch",
            config={"displayModeBar": False},
        )
        st.caption(
            "Dotted lines mark administration times. Gaps mark bolus jumps. "
            "Peak concentration and time are sampled estimates across the full history."
        )
    response_col, schedule_col = st.columns([1.35, 1])
    with response_col, st.container(border=True):
        st.subheader("Pharmacodynamic response")
        st.caption(
            f"{scenario.pd.model.replace('_', ' ').title()} · "
            f"{scenario.pd.driver.replace('_', ' ')} driver"
        )
        response_breaks = (
            bolus_times
            if scenario.pd.driver == "plasma" and not scenario.pd.model.startswith("indirect")
            else ()
        )
        st.plotly_chart(
            chart(
                frame,
                {"effect": "Response"},
                "Response (arbitrary units)",
                breaks=response_breaks,
                height=280,
            ),
            width="stretch",
            config={"displayModeBar": False},
        )
    with schedule_col, st.container(border=True):
        st.subheader("Dose schedule")
        st.caption("Explicit administrations · hours / milligrams")
        schedule = pd.DataFrame([d.model_dump() for d in scenario.doses])
        if schedule.empty:
            st.info("No doses. This experiment follows the drug-free baseline.")
        else:
            st.dataframe(
                schedule,
                hide_index=True,
                height=280,
                width="stretch",
                column_config={
                    "time_h": "Time (h)",
                    "amount_mg": "Dose (mg)",
                    "route": "Route",
                    "duration_h": "Duration (h)",
                },
            )
    with st.expander("Mass accounting & interpretation"):
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
                breaks=dose_times,
            ),
            width="stretch",
        )
        st.caption(
            "Maximum absolute mass balance residual: "
            f"{summary['max_abs_mass_balance_error_mg']:.2e} mg. "
            "AUC is integrated through the simulation horizon, not to infinity. "
            "Peripheral compartments are abstract distribution spaces."
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
        try:
            r = simulate(candidate)
        except (ValueError, RuntimeError) as exc:
            st.error(f"Model comparison could not be completed: {exc}")
            st.stop()
        comparison_data[f"model_{n}"] = r.frame.central_mg_l
        comparison_rows.append({"PK compartments": n, **r.summary()})
    st.plotly_chart(
        chart(
            comparison_data,
            {f"model_{n}": f"{n} compartment" for n in (1, 2, 3)},
            "Central concentration (mg/L)",
            breaks=bolus_times,
            dose_times=dose_times,
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
            try:
                bands = population(
                    scenario, subjects=subjects, clearance_cv=cl_cv, volume_cv=v_cv, seed=seed
                )
            except (ValueError, RuntimeError) as exc:
                st.session_state.pop("population_result", None)
                st.error(f"Population experiment could not be completed: {exc}")
                st.stop()
            st.session_state["population_result"] = (population_key, bands)
    stored_population = st.session_state.get("population_result")
    if stored_population is not None and stored_population[0] == population_key:
        bands = stored_population[1]
        fig = chart(
            bands,
            {"p05_mg_l": "5th percentile", "p50_mg_l": "Median", "p95_mg_l": "95th percentile"},
            "Central concentration (mg/L)",
            breaks=bolus_times,
        )
        fig.data[0].line.width = 0
        fig.data[1].line.color = "#087f8c"
        fig.data[2].line.width = 0
        # Order lower, upper, median so the shaded area spans the requested percentiles.
        fig.data = (fig.data[0], fig.data[2], fig.data[1])
        fig.data[1].fill = "tonexty"
        fig.data[1].fillcolor = "rgba(8,127,140,0.12)"
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
        "of clinical variability. No measurement noise or parameter uncertainty is included. "
        "Band edges also vary with the number of subjects and random seed."
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
        except (ValueError, RuntimeError) as exc:
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
st.caption("PK/PD Lab · UMWai · Research and education. Not validated for clinical dosing.")

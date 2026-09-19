from math import exp

import numpy as np
import pytest
from numpy.testing import assert_allclose
from pydantic import ValidationError
from scipy.linalg import expm

from pkpd_lab import Dose, PDParameters, PKParameters, Scenario, repeated_doses, simulate


def one_compartment(**updates):
    return PKParameters.model_validate(
        {
            "central_volume_l": 20,
            "clearance_l_h": 4,
            "peripheral_volumes_l": (),
            "intercompartmental_clearances_l_h": (),
            **updates,
        }
    )


def test_iv_bolus_matches_analytic_concentration_and_auc():
    r = simulate(Scenario(pk=one_compartment(), doses=(Dose(route="iv_bolus"),)))
    t = r.frame.time_h.to_numpy()
    assert_allclose(r.frame.central_mg_l, 5 * np.exp(-0.2 * t), atol=2e-7)
    assert_allclose(r.frame.auc_mg_h_l, 25 * (1 - np.exp(-0.2 * t)), atol=2e-7)
    assert r.summary()["max_abs_mass_balance_error_mg"] < 1e-7


@pytest.mark.parametrize("ka", [1.2, 0.2])
def test_oral_matches_bateman_including_equal_rates(ka):
    pk = one_compartment(absorption_rate_h=ka, bioavailability=0.7)
    frame = simulate(Scenario(pk=pk)).frame
    t = frame.time_h.to_numpy()
    expected = (
        3.5 * ka / (ka - 0.2) * (np.exp(-0.2 * t) - np.exp(-ka * t))
        if ka != 0.2
        else 3.5 * ka * t * np.exp(-ka * t)
    )
    assert_allclose(frame.central_mg_l, expected, atol=2e-7)


@pytest.mark.parametrize("n", [2, 3])
def test_multicompartment_matches_independent_matrix_exponential(n):
    volumes = np.array([20, 30, 80][:n])
    qs = np.array([6, 3][: n - 1])
    pk = PKParameters(
        central_volume_l=volumes[0],
        peripheral_volumes_l=tuple(volumes[1:]),
        intercompartmental_clearances_l_h=tuple(qs),
    )
    matrix = np.zeros((n, n))
    matrix[0, 0] = -(4 + qs.sum()) / volumes[0]
    for j, q in enumerate(qs, start=1):
        matrix[0, j] = q / volumes[j]
        matrix[j, 0] = q / volumes[0]
        matrix[j, j] = -q / volumes[j]
    initial = np.zeros(n)
    initial[0] = 100
    frame = simulate(Scenario(pk=pk, doses=(Dose(route="iv_bolus"),), samples=73)).frame
    expected = np.array([expm(matrix * t) @ initial / volumes for t in frame.time_h])
    columns = ["central_mg_l"] + [f"peripheral_{j}_mg_l" for j in range(1, n)]
    assert_allclose(frame[columns], expected, atol=2e-7)


def test_off_grid_repeated_bolus_superposition_and_right_continuity():
    doses = repeated_doses(100, 3.73, 4, route="iv_bolus")
    frame = simulate(Scenario(pk=one_compartment(), doses=doses, samples=19)).frame
    t = frame.time_h.to_numpy()
    expected = sum(np.where(t >= d.time_h, 5 * np.exp(-0.2 * (t - d.time_h)), 0) for d in doses)
    assert_allclose(frame.central_mg_l, expected, atol=3e-7)
    for d in doses:
        assert d.time_h in t


def test_overlapping_infusions_match_superposition():
    doses = (
        Dose(route="iv_infusion", duration_h=5),
        Dose(time_h=2.3, amount_mg=60, route="iv_infusion", duration_h=4),
    )
    frame = simulate(Scenario(pk=one_compartment(), doses=doses, end_h=20, samples=57)).frame
    expected = np.zeros(len(frame))
    t = frame.time_h.to_numpy()
    for dose in doses:
        elapsed = np.maximum(t - dose.time_h, 0)
        expected += (
            dose.amount_mg
            / dose.duration_h
            / 4
            * (1 - np.exp(-0.2 * np.minimum(elapsed, dose.duration_h)))
            * np.exp(-0.2 * np.maximum(elapsed - dose.duration_h, 0))
        )
    assert_allclose(frame.central_mg_l, expected, atol=2e-7)
    assert_allclose(frame.administered_mg.iloc[-1], 160)


def test_infusion_crossing_end_accounts_only_delivered_amount():
    frame = simulate(
        Scenario(
            pk=one_compartment(),
            end_h=3,
            doses=(Dose(time_h=1, route="iv_infusion", duration_h=10),),
        )
    ).frame
    assert frame.administered_mg.iloc[-1] == 20
    assert abs(frame.mass_balance_error_mg.iloc[-1]) < 1e-7


def test_lag_and_f_are_accounted_once_with_repeated_doses():
    pk = one_compartment(absorption_lag_h=2.37, bioavailability=0.6)
    doses = repeated_doses(100, 4.17, 3)
    frame = simulate(Scenario(pk=pk, doses=doses, end_h=10, samples=63)).frame
    assert (frame.loc[frame.time_h <= 2.37, "central_mg_l"] == 0).all()
    last = frame.iloc[-1]
    assert last.administered_mg == 300
    assert last.pending_lag_mg == 100
    assert last.unavailable_mg == 80
    assert abs(last.mass_balance_error_mg) < 1e-7


def test_dose_at_end_and_simultaneous_unsorted_doses():
    scenario = Scenario(
        pk=one_compartment(),
        end_h=10,
        doses=(Dose(time_h=10, route="iv_bolus"), Dose(route="iv_bolus"), Dose(route="iv_bolus")),
    )
    frame = simulate(scenario).frame
    assert frame.central_mg_l.iloc[0] == 10
    assert_allclose(frame.central_mg_l.iloc[-1], 10 * exp(-2) + 5, atol=1e-7)
    assert_allclose(frame.auc_mg_h_l.iloc[-1], 50 * (1 - exp(-2)), atol=1e-7)


def test_pure_saturable_elimination_matches_integrated_mm_equation():
    pk = one_compartment(clearance_l_h=0, vmax_mg_h=5, km_mg_l=2)
    frame = simulate(Scenario(pk=pk, doses=(Dose(route="iv_bolus"),), end_h=10)).frame
    a = frame.central_mg.to_numpy()
    time_from_amount = (100 - a + 40 * np.log(100 / a)) / 5
    assert_allclose(time_from_amount, frame.time_h, atol=2e-6)


@pytest.mark.parametrize("n", [1, 2, 3])
def test_mixed_routes_conserve_mass_with_nonlinear_elimination(n):
    pk = PKParameters(
        peripheral_volumes_l=(30, 80)[: n - 1],
        intercompartmental_clearances_l_h=(6, 3)[: n - 1],
        absorption_lag_h=1.7,
        vmax_mg_h=10,
    )
    doses = (
        Dose(),
        Dose(time_h=3.4, route="iv_bolus"),
        Dose(time_h=2.6, route="iv_infusion", duration_h=9.2),
    )
    result = simulate(Scenario(pk=pk, doses=doses))
    assert result.summary()["max_abs_mass_balance_error_mg"] < 1e-6


def test_effect_site_matches_analytic_solution():
    scenario = Scenario(
        pk=one_compartment(),
        pd=PDParameters(effect_equilibration_h=0.5),
        doses=(Dose(route="iv_bolus"),),
    )
    frame = simulate(scenario).frame
    t = frame.time_h.to_numpy()
    ce = 5 * 0.5 / (0.5 - 0.2) * (np.exp(-0.2 * t) - np.exp(-0.5 * t))
    assert_allclose(frame.effect_site_mg_l, ce, atol=2e-7)
    assert_allclose(frame.effect, 100 * ce / (2 + ce), atol=2e-6)


@pytest.mark.parametrize("model", ["emax", "linear", "indirect_inhibition", "indirect_stimulation"])
def test_no_drug_preserves_pd_baseline(model):
    pd = PDParameters(model=model, baseline=100, maximum_effect=0.8)
    frame = simulate(Scenario(pd=pd, doses=())).frame
    assert_allclose(frame.effect, 100)
    assert_allclose(frame.central_mg_l, 0)


@pytest.mark.parametrize(
    "model, factor", [("indirect_inhibition", 0.6), ("indirect_stimulation", 1.4)]
)
def test_indirect_response_matches_constant_concentration_solution(model, factor):
    pd = PDParameters(
        model=model,
        driver="plasma",
        baseline=100,
        maximum_effect=0.8,
        ec50_mg_l=5,
        turnover_rate_h=0.2,
    )
    frame = simulate(
        Scenario(pk=one_compartment(clearance_l_h=0), pd=pd, doses=(Dose(route="iv_bolus"),))
    ).frame
    expected = 100 * factor + (100 - 100 * factor) * np.exp(-0.2 * frame.time_h)
    assert_allclose(frame.effect, expected, atol=3e-6)


def test_zero_bioavailability_has_no_systemic_exposure():
    frame = simulate(Scenario(pk=one_compartment(bioavailability=0))).frame
    assert_allclose(frame.central_mg_l, 0)
    assert_allclose(frame.unavailable_mg, 100)


@pytest.mark.parametrize("times", [[1, 1], [2, 1], [-1, 1], [0, 49], [0, np.nan], [], [[1, 2]]])
def test_invalid_observation_times_are_rejected(times):
    with pytest.raises(ValueError):
        simulate(Scenario(), times=times)


def test_custom_times_include_boundaries_and_match_values():
    frame = simulate(
        Scenario(pk=one_compartment(), doses=(Dose(route="iv_bolus"),)), times=[1.23, 4.56]
    ).frame
    assert_allclose(frame.time_h, [0, 1.23, 4.56, 48])
    assert_allclose(frame.central_mg_l, 5 * np.exp(-0.2 * frame.time_h), atol=1e-7)


@pytest.mark.parametrize(
    "data",
    [
        {"central_volume_l": 0},
        {"clearance_l_h": -1},
        {"clearance_l_h": float("nan")},
        {"absorption_rate_h": float("inf")},
        {"bioavailability": 1.1},
        {"km_mg_l": 0},
        {"peripheral_volumes_l": (10,) * 3},
        {"intercompartmental_clearances_l_h": ()},
        {"clearence_l_h": 5},
    ],
)
def test_invalid_pk_rejected(data):
    with pytest.raises(ValidationError):
        PKParameters.model_validate(data)


@pytest.mark.parametrize(
    "data",
    [
        {"route": "iv_infusion"},
        {"duration_h": 1},
        {"amount_mg": -1},
        {"time_h": -1},
        {"route": "unknown"},
    ],
)
def test_invalid_doses_rejected(data):
    with pytest.raises(ValidationError):
        Dose.model_validate(data)


def test_invalid_horizon_and_indirect_inhibition_rejected():
    with pytest.raises(ValidationError):
        Scenario(doses=(Dose(time_h=50),))
    with pytest.raises(ValidationError):
        PDParameters(model="indirect_inhibition", baseline=100, maximum_effect=2)


def test_json_round_trip_and_provenance_validation():
    original = Scenario(doses=repeated_doses(100, 12, 4))
    assert Scenario.model_validate_json(original.model_dump_json()) == original
    with pytest.raises(ValidationError):
        Scenario(provenance={"kind": "literature"})
    with pytest.raises(ValidationError):
        Scenario(schema_version=2)


@pytest.mark.parametrize(
    "count,interval", [(0, 12), (True, 12), (1.5, 12), (2, 0), (2, float("nan"))]
)
def test_invalid_repeated_schedule_rejected(count, interval):
    with pytest.raises(ValueError):
        repeated_doses(100, interval, count)

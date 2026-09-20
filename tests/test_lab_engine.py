import io
import json
import zipfile

import numpy as np
import pytest
from numpy.testing import assert_allclose
from pydantic import ValidationError

from pkpd_lab import PKParameters, Scenario, repeated_doses, simulate
from pkpd_lab.expressions import Expression, unit_dimension
from pkpd_lab.lab_engine import export_run, generate_lab, simulate_lab
from pkpd_lab.lab_models import (
    Compartment,
    Equation,
    KineticProcess,
    Lab,
    LabDose,
    Parameter,
    Subject,
)
from pkpd_lab.lab_store import save_lab, saved_labs
from pkpd_lab.lab_templates import example_lab, new_subject


def run_subject(subject, end=10, samples=101):
    lab = Lab(subjects=(subject,), end_h=end, samples=samples)
    return simulate_lab(lab)[subject.id]


@pytest.mark.parametrize("order", [0, 1, 2, 3])
def test_kinetic_orders_against_analytic_amounts(order):
    subject = Subject(
        compartments=(Compartment(symbol="a", name="A", volume_l=2, initial_mg=10),),
        processes=(KineticProcess(name="Loss", source="a", kinetic_order=order, coefficient=2),),
    )
    frame = run_subject(subject)
    t = frame.time_h.to_numpy()
    k = 2 / 2**order
    if order == 0:
        expected = np.maximum(10 - k * t, 0)
    elif order == 1:
        expected = 10 * np.exp(-k * t)
    else:
        expected = (10 ** (1 - order) + (order - 1) * k * t) ** (1 / (1 - order))
    assert_allclose(frame.a, expected, atol=3e-7, rtol=2e-7)
    assert frame.mass_balance_error_mg.abs().max() < 1e-7


def test_zero_order_transfer_exhausts_and_pulse_refills_without_negative_amounts():
    subject = Subject(
        compartments=(
            Compartment(symbol="a", name="A", initial_mg=10),
            Compartment(symbol="b", name="B"),
        ),
        processes=(
            KineticProcess(name="Transfer", source="a", target="b", kinetic_order=0, coefficient=2),
        ),
        doses=(LabDose(time_h=8, target="a", amount_mg=4),),
    )
    frame = run_subject(subject, end=12)
    t = frame.time_h.to_numpy()
    expected = np.maximum(10 - 2 * t, 0) + np.where(t >= 8, np.maximum(4 - 2 * (t - 8), 0), 0)
    assert_allclose(frame.a, expected, atol=1e-7)
    assert_allclose(frame.b, 10 + 4 * (t >= 8) - expected, atol=1e-7)
    assert frame.a.min() >= 0
    assert frame.b.iloc[-1] == pytest.approx(14)


def test_zero_order_source_cycles_are_rejected_explicitly():
    with pytest.raises(ValidationError, match="Cycles"):
        Subject(
            compartments=(Compartment(symbol="a", name="A"), Compartment(symbol="b", name="B")),
            processes=(
                KineticProcess(name="In", source="a", target="b", kinetic_order=0),
                KineticProcess(name="Out", source="b", target="a", kinetic_order=0),
            ),
        )


@pytest.mark.parametrize("capacity", [10, 200])
def test_zero_order_elimination_with_continuous_absorption(capacity):
    subject = Subject(
        compartments=(
            Compartment(symbol="gut", name="Gut", volume_l=1),
            Compartment(symbol="central", name="Central", volume_l=20),
        ),
        processes=(
            KineticProcess(name="Absorb", source="gut", target="central", coefficient=1),
            KineticProcess(
                name="Eliminate", source="central", kinetic_order=0, coefficient=capacity
            ),
        ),
        doses=(LabDose(target="gut", amount_mg=100),),
    )
    frame = run_subject(subject, end=20)
    absorbed = 100 * (1 - np.exp(-frame.time_h))
    expected = np.maximum(absorbed - capacity * frame.time_h, 0)
    assert_allclose(frame.central, expected, atol=2e-6)
    assert_allclose(frame.eliminated_mg, absorbed - expected, atol=2e-6)
    assert frame.mass_balance_error_mg.abs().max() < 1e-6


def test_stale_lab_results_cannot_be_exported_with_changed_parameters():
    lab = example_lab()
    results = simulate_lab(lab)
    changed = Lab.model_validate(lab.model_dump() | {"end_h": 72})
    with pytest.raises(ValueError, match="different lab configuration"):
        export_run(changed, results)


@pytest.mark.parametrize("n", [1, 2, 3])
def test_generated_pk_template_matches_existing_engine(n):
    subject = new_subject("Reference", f"{n} compartment" if n == 1 else f"{n} compartments")
    frame = run_subject(subject, end=48, samples=481)
    pk = PKParameters(
        bioavailability=1,
        peripheral_volumes_l=(30, 80)[: n - 1],
        intercompartmental_clearances_l_h=(6, 3)[: n - 1],
    )
    reference = simulate(Scenario(pk=pk, doses=repeated_doses(100, 12, 4))).frame
    assert_allclose(frame.central_C, reference.central_mg_l, atol=3e-6)


@pytest.mark.parametrize("order", [1, 2, 3])
def test_derivative_orders_against_polynomial_solution(order):
    subject = Subject(
        parameters=(Parameter(symbol="drive", value=2, unit=f"response/h^{order}"),),
        equations=(
            Equation(
                symbol="x",
                derivative_order=order,
                rhs="drive",
                initial=tuple([1] + [0] * (order - 1)),
            ),
        ),
    )
    frame = run_subject(subject, end=4)
    import math

    assert_allclose(frame.x, 1 + 2 * frame.time_h**order / math.factorial(order), atol=1e-7)


def test_second_order_oscillator_and_algebraic_dependency_sorting():
    subject = Subject(
        parameters=(Parameter(symbol="omega2", value=1, unit="1/h^2"),),
        equations=(
            Equation(symbol="z", derivative_order=0, rhs="y + x", initial=()),
            Equation(symbol="y", derivative_order=0, rhs="2 * x", initial=()),
            Equation(symbol="x", derivative_order=2, rhs="-omega2 * x", initial=(1, 0)),
        ),
    )
    frame = run_subject(subject)
    assert_allclose(frame.x, np.cos(frame.time_h), atol=4e-8)
    assert_allclose(frame.x_d1, -np.sin(frame.time_h), atol=4e-8)
    assert_allclose(frame.z, 3 * np.cos(frame.time_h), atol=2e-7)


def test_algebraic_only_time_function_and_zero_rhs():
    subject = Subject(
        parameters=(Parameter(symbol="rate", value=2, unit="response/h"),),
        equations=(
            Equation(symbol="x", derivative_order=0, rhs="rate * t", initial=()),
            Equation(symbol="flat", derivative_order=3, rhs="0", initial=(3, 0, 0)),
        ),
    )
    frame = run_subject(subject)
    assert_allclose(frame.x, 2 * frame.time_h)
    assert_allclose(frame.flat, 3)


def test_equation_references_cannot_cross_subject_boundaries():
    a = Subject(equations=(Equation(symbol="x", rhs="0"),))
    b = Subject(equations=(Equation(symbol="y", rhs="x"),))
    with pytest.raises(ValueError, match="Unknown symbol"):
        generate_lab(Lab(subjects=(a, b)))


def test_algebraic_cycles_and_unit_mismatches_rejected():
    cycle = Subject(
        equations=(
            Equation(symbol="x", derivative_order=0, rhs="y", initial=()),
            Equation(symbol="y", derivative_order=0, rhs="x", initial=()),
        )
    )
    with pytest.raises(ValueError, match="cycle"):
        generate_lab(Lab(subjects=(cycle,)))
    mismatch = Subject(equations=(Equation(symbol="x", rhs="x"),))
    with pytest.raises(ValueError, match="units"):
        generate_lab(Lab(subjects=(mismatch,)))


@pytest.mark.parametrize(
    "source",
    [
        "__import__('os').system('id')",
        "x.__class__",
        "x[0]",
        "[x for x in [1]]",
        "lambda: 1",
        "open('file')",
        "exp(x)",
        "x ** 1000",
        "unknown",
    ],
)
def test_unsafe_or_dimensionally_invalid_expressions_rejected(source):
    with pytest.raises(ValueError):
        Expression.compile(source, {"x": unit_dimension("mg")}, unit_dimension("mg"))


def test_runtime_expression_domain_errors_are_explicit():
    subject = Subject(
        equations=(
            Equation(symbol="x", derivative_order=0, rhs="log(t / t)", unit="1", initial=()),
        )
    )
    with pytest.raises(ValueError, match="Expression failed"):
        run_subject(subject)


def test_subjects_remain_independent_and_export_is_reproducible():
    lab = example_lab()
    results = simulate_lab(lab)
    a, b = lab.subjects
    assert results[b.id].central_C.iloc[-1] > results[a.id].central_C.iloc[-1]
    assert_allclose(results[a.id].central_C, run_subject(a, end=48, samples=481).central_C)
    with zipfile.ZipFile(io.BytesIO(export_run(lab, results))) as bundle:
        restored = Lab.model_validate_json(bundle.read("lab.json"))
        manifest = json.loads(bundle.read("manifest.json"))
        assert restored == lab
        assert len(manifest["output_sha256"]) == 2
        assert manifest["versions"]["pandas"]
        assert len(manifest["lab_sha256"]) == 64


def test_storage_roundtrip_invalid_files_and_path_validation(tmp_path):
    lab = example_lab()
    save_lab(lab, tmp_path)
    loaded, errors = saved_labs(tmp_path)
    assert loaded == [lab] and not errors
    (tmp_path / "broken.json").write_text("{}")
    loaded, errors = saved_labs(tmp_path)
    assert loaded == [lab] and errors
    with pytest.raises(ValidationError):
        Lab(id="../../outside")


def test_wrong_initial_count_and_reserved_names_are_rejected():
    with pytest.raises(ValidationError):
        Equation(symbol="x", derivative_order=3, rhs="0", initial=(0,))
    with pytest.raises(ValidationError):
        Subject(compartments=(Compartment(symbol="eliminated_mg", name="Invalid"),))

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_workbench_starts_and_switches_compartments_and_route():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    assert len(app.metric) == 4
    app.select_slider[0].set_value(3).run()
    assert not app.exception
    next(x for x in app.selectbox if x.label == "Administration").select("IV infusion").run()
    assert not app.exception
    assert not app.error


def test_indirect_response_and_variability_controls_work():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    next(x for x in app.selectbox if x.label == "Response model").select(
        "indirect_inhibition"
    ).run()
    assert not app.exception
    assert not app.error
    next(x for x in app.slider if x.label == "Virtual subjects").set_value(10)
    next(x for x in app.button if x.label == "Run virtual population").click().run()
    assert not app.exception
    next(x for x in app.button if x.label == "Compare −20%, baseline, +20%").click().run()
    assert not app.exception
    assert "population_result" in app.session_state
    assert "sensitivity_result" in app.session_state
    # Unrelated reruns retain results; changed assumptions must hide obsolete bands.
    app.run()
    assert any(x.label == "Download population bands" for x in app.get("download_button"))
    next(x for x in app.slider if x.label == "Clearance CV").set_value(0.4).run()
    assert not any(x.label == "Download population bands" for x in app.get("download_button"))


def test_invalid_horizon_shows_error_instead_of_silently_dropping_doses():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    next(x for x in app.number_input if x.label == "Simulation horizon (h)").set_value(10).run()
    assert app.error
    assert not app.exception


def test_import_hides_builder_and_linear_pd_shows_relevant_parameters():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    next(x for x in app.selectbox if x.label == "Response model").select("linear").run()
    labels = {x.label for x in app.number_input}
    assert "Linear slope (response per mg/L)" in labels
    assert "EC50 / IC50 (mg/L)" not in labels
    app.radio[0].set_value("Import JSON").run()
    assert not app.number_input
    assert not app.exception


@pytest.mark.parametrize("path", ["comparison", "population"])
def test_experiment_solver_failure_is_reported_without_traceback(monkeypatch, path):
    if path == "comparison":
        import pkpd_lab

        original = pkpd_lab.simulate
        calls = 0

        def fail_comparison(scenario):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("Injected integration failure")
            return original(scenario)

        monkeypatch.setattr(pkpd_lab, "simulate", fail_comparison)
    else:
        import pkpd_lab.experiments

        def fail_population(*args, **kwargs):
            raise RuntimeError("Injected integration failure")

        monkeypatch.setattr(pkpd_lab.experiments, "population", fail_population)
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    if path == "population":
        next(x for x in app.button if x.label == "Run virtual population").click().run()
    assert app.error
    assert "Injected integration failure" in app.error[0].value
    assert not app.exception

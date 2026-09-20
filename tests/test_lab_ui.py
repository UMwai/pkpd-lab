from pathlib import Path

from streamlit.testing.v1 import AppTest

from pkpd_lab.lab_models import Lab
from pkpd_lab.lab_store import saved_labs

APP = Path(__file__).resolve().parents[1] / "app.py"


def button(app, label):
    return next(x for x in app.button if x.label == label)


def test_create_add_generate_run_save_and_restore_lab():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    button(app, "Create lab").click().run()
    assert not app.exception
    button(app, "Add body").click().run()
    assert not app.exception
    button(app, "Generate model").click().run()
    assert not app.exception and not app.error
    button(app, "Run simulation").click().run()
    assert not app.exception and not app.error
    assert "lab_run" in app.session_state
    button(app, "Save lab").click().run()
    loaded, errors = saved_labs()
    assert len(loaded) == 1 and not errors
    assert loaded[0] == Lab.model_validate(app.session_state["active_lab"])
    button(app, "Save & create another lab").click().run()
    button(app, "Open saved lab").click().run()
    assert Lab.model_validate(app.session_state["active_lab"]) == loaded[0]


def test_adding_body_invalidates_generated_model_and_results():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    button(app, "Open example lab").click().run()
    button(app, "Generate model").click().run()
    button(app, "Run simulation").click().run()
    assert not app.exception and not app.error
    button(app, "Duplicate selected body").click().run()
    assert len(app.session_state["active_lab"]["subjects"]) == 3
    assert not any(x.label == "Run simulation" for x in app.button)
    assert not any(x.label == "Download complete run" for x in app.get("download_button"))


def test_higher_order_body_template_can_be_generated_and_run():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    button(app, "Create lab").click().run()
    next(x for x in app.selectbox if x.label == "Starting model").select("Higher-order example")
    button(app, "Add body").click().run()
    button(app, "Generate model").click().run()
    button(app, "Run simulation").click().run()
    assert not app.exception and not app.error
    result = app.session_state["lab_run"][1]
    assert "oscillator_d1" in next(iter(result.values())).columns
    assert "third_d2" in next(iter(result.values())).columns


def test_bad_equation_rejects_generation_and_hides_previous_results():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    button(app, "Open example lab").click().run()
    button(app, "Generate model").click().run()
    lab = app.session_state["active_lab"]
    lab["subjects"][0]["equations"][0]["rhs"] = "unknown_symbol"
    app.session_state["active_lab"] = lab
    app.run()
    button(app, "Generate model").click().run()
    assert app.error and not app.exception
    assert "Unknown symbol" in app.error[0].value

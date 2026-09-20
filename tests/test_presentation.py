import pandas as pd

from pkpd_lab import PKParameters, Scenario
from pkpd_lab.presentation import chart, model_diagram


def test_bolus_plot_breaks_do_not_modify_numerical_data():
    frame = pd.DataFrame({"time_h": [0.0, 1.0, 2.0], "central_mg_l": [0.0, 5.0, 4.0]})
    original = frame.copy(deep=True)
    fig = chart(frame, {"central_mg_l": "Central"}, "mg/L", breaks=[1.0])
    assert list(fig.data[0].y) == [0.0, None, 5.0, 4.0]
    assert list(fig.data[0].x) == [0.0, 1.0, 1.0, 2.0]
    assert fig.data[0].connectgaps is False
    assert frame.equals(original)


def test_log_plot_omits_zero_without_inventing_a_floor():
    frame = pd.DataFrame({"time_h": [0.0, 1.0], "central_mg_l": [0.0, 2.0]})
    fig = chart(frame, {"central_mg_l": "Central"}, "mg/L", log=True)
    assert list(fig.data[0].y) == [None, 2.0]
    assert fig.layout.yaxis.type == "log"


def test_three_compartment_map_links_both_peripherals_to_central():
    scenario = Scenario(
        pk=PKParameters(peripheral_volumes_l=(30, 80), intercompartmental_clearances_l_h=(6, 3))
    )
    diagram = model_diagram(scenario)
    assert diagram.count('class="peripheral-link"') == 2
    assert "Q1 6 L/h" in diagram
    assert "Q2 3 L/h" in diagram

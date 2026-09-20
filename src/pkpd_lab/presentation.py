"""Presentation helpers. These do not change the simulated trajectories."""

from html import escape

import plotly.graph_objects as go

from .models import Scenario

PALETTE = ["#087f8c", "#c97836", "#6960b5", "#3f7e54"]


def model_diagram(scenario: Scenario) -> str:
    """Compact, accessible topology diagram; every peripheral links to central."""
    pk = scenario.pk
    oral = any(d.route == "oral" for d in scenario.doses)
    input_label = "Oral depot" if oral else "IV input"
    input_detail = (
        f"ka {pk.absorption_rate_h:g} /h · F {pk.bioavailability:g}"
        if oral
        else "Direct to central"
    )
    if oral and any(d.route != "oral" for d in scenario.doses):
        input_detail += " · + IV to central"
    if not scenario.doses:
        input_label, input_detail = "No dose", "Drug-free baseline"
    peripherals = "".join(
        f'<div class="peripheral-link"><span class="exchange">↔ Q{i + 1} {q:g} L/h</span>'
        f'<div class="model-node"><small>PERIPHERAL {i + 1}</small><b>{v:g} L</b></div></div>'
        for i, (v, q) in enumerate(
            zip(pk.peripheral_volumes_l, pk.intercompartmental_clearances_l_h, strict=True)
        )
    )
    output = f"CL {pk.clearance_l_h:g} L/h"
    if pk.vmax_mg_h > 0:
        output += f" + Vmax {pk.vmax_mg_h:g} mg/h"
    return (
        '<div class="model-map" role="img" aria-label="PK model topology: input to central, '
        'central exchanges with each peripheral, elimination from central">'
        f'<div class="model-node input-node"><small>{escape(input_label.upper())}</small>'
        f'<b>{escape(input_detail)}</b></div><span class="model-arrow">→</span>'
        '<div class="model-node central-node"><small>CENTRAL</small>'
        f"<b>{pk.central_volume_l:g} L</b>"
        f"<span>↓ {escape(output)}</span></div>"
        f'<div class="peripheral-stack">{peripherals}</div></div>'
    )


def chart(data, columns, y_label, *, log=False, breaks=(), dose_times=(), height=365):
    """Plot sampled values, breaking lines before instantaneous jumps.

    `breaks` lists discontinuities for all plotted columns. A gap avoids implying
    a finite infusion ramp; exported data and numerical metrics are unchanged.
    """
    fig = go.Figure()
    breaks = set(breaks)
    for i, (column, name) in enumerate(columns.items()):
        x, y = [], []
        for time, value in zip(data.time_h, data[column], strict=True):
            if time in breaks:
                x.append(time)
                y.append(None)
            x.append(time)
            y.append(None if log and value <= 0 else value)
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                name=name,
                mode="lines+markers",
                connectgaps=False,
                line={"color": PALETTE[i % len(PALETTE)], "width": 2.5},
                marker={
                    "size": [
                        5 if time in breaks and value is not None else 0
                        for time, value in zip(x, y, strict=True)
                    ],
                    "color": PALETTE[i % len(PALETTE)],
                },
                hovertemplate="%{y:.3f}<extra>%{fullData.name}</extra>",
            )
        )
    for time in sorted(set(dose_times))[:100]:
        fig.add_vline(x=time, line_width=1, line_dash="dot", line_color="#dbe4ec", layer="below")
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Trebuchet MS, sans-serif", "color": "#52647b", "size": 12},
        margin={"l": 12, "r": 18, "t": 50, "b": 12},
        height=height,
        xaxis_title="Time (h)",
        yaxis_title=y_label,
        legend={"orientation": "h", "y": 1.16, "x": 0, "font": {"size": 12}},
        hovermode="x unified",
        hoverlabel={"bgcolor": "#ffffff", "font_size": 13},
    )
    fig.update_xaxes(gridcolor="#edf1f5", zeroline=False, ticks="outside", tickcolor="#dbe4ec")
    fig.update_yaxes(
        type="log" if log else "linear",
        gridcolor="#edf1f5",
        zeroline=False,
        rangemode="normal" if log else "tozero",
    )
    return fig

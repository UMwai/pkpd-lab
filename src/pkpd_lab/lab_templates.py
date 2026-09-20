"""Synthetic starting points; coefficients are illustrative, not drug calibrations."""

from .lab_models import Compartment, Equation, KineticProcess, Lab, LabDose, Parameter, Subject


def new_subject(name: str, template: str = "2 compartments") -> Subject:
    if template == "Empty equation system":
        return Subject(name=name)
    if template == "Higher-order example":
        return Subject(
            name=name,
            notes="Synthetic mathematics example; not a drug-response model",
            parameters=(
                Parameter(symbol="omega2", value=1, unit="1/h^2"),
                Parameter(symbol="jerk", value=0.1, unit="response/h^3"),
            ),
            equations=(
                Equation(
                    symbol="oscillator",
                    derivative_order=2,
                    unit="response",
                    rhs="-omega2 * oscillator",
                    initial=(1, 0),
                ),
                Equation(
                    symbol="third",
                    derivative_order=3,
                    unit="response",
                    rhs="jerk",
                    initial=(0, 0, 0),
                ),
                Equation(
                    symbol="combined",
                    derivative_order=0,
                    unit="response",
                    rhs="oscillator + third",
                    initial=(),
                ),
            ),
        )
    if template not in ("1 compartment", "2 compartments", "3 compartments"):
        raise ValueError("Unknown body template")
    n = int(template[0])
    compartments = [
        Compartment(symbol="gut", name="Absorption depot", volume_l=1),
        Compartment(symbol="central", name="Central", volume_l=20),
    ]
    processes = [
        KineticProcess(name="Absorption", source="gut", target="central", coefficient=1.2),
        KineticProcess(name="Elimination", source="central", coefficient=4),
    ]
    for i in range(n - 1):
        symbol = f"peripheral{i + 1}"
        compartments.append(
            Compartment(symbol=symbol, name=f"Peripheral {i + 1}", volume_l=(30, 80)[i])
        )
        for source, target in (("central", symbol), (symbol, "central")):
            processes.append(
                KineticProcess(
                    name=f"{source} to {target}",
                    source=source,
                    target=target,
                    coefficient=(6, 3)[i],
                )
            )
    return Subject(
        name=name,
        compartments=tuple(compartments),
        processes=tuple(processes),
        parameters=(
            Parameter(symbol="emax", value=100, unit="response"),
            Parameter(symbol="ec50", value=2, unit="mg/L"),
        ),
        equations=(
            Equation(
                symbol="effect",
                derivative_order=0,
                initial=(),
                rhs="emax * central_C / (ec50 + central_C)",
            ),
        ),
        doses=tuple(LabDose(time_h=t, target="gut", amount_mg=100) for t in (0, 12, 24, 36)),
    )


def example_lab() -> Lab:
    a = new_subject("Reference body")
    b = new_subject("Slower clearance")
    data = b.model_dump()
    data["processes"][1]["coefficient"] = 2
    b = Subject.model_validate(data)
    return Lab(
        name="Clearance comparison",
        description="Two synthetic bodies; same dose history, "
        "different linear elimination coefficients. Bioavailability is 1 in both.",
        subjects=(a, b),
    )

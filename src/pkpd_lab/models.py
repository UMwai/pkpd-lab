"""Validated, serializable model definitions. All examples are synthetic."""

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Nonnegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Finite = Annotated[float, Field(allow_inf_nan=False)]


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PKParameters(Model):
    """Mammillary model: central compartment connected to 0, 1, or 2 peripherals."""

    clearance_l_h: Nonnegative = 4.0
    central_volume_l: Positive = 20.0
    peripheral_volumes_l: tuple[Positive, ...] = (30.0,)
    intercompartmental_clearances_l_h: tuple[Nonnegative, ...] = (6.0,)
    absorption_rate_h: Positive = 1.2
    bioavailability: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 0.8
    absorption_lag_h: Nonnegative = 0.0
    # An optional pathway in addition to linear clearance (set CL=0 for pure MM).
    vmax_mg_h: Nonnegative = 0.0
    km_mg_l: Positive = 2.0

    @model_validator(mode="after")
    def check_structure(self):
        n = len(self.peripheral_volumes_l)
        if n > 2 or len(self.intercompartmental_clearances_l_h) != n:
            raise ValueError("Provide 0–2 peripheral volumes with one matching Q per volume")
        return self

    @property
    def compartments(self) -> int:
        return 1 + len(self.peripheral_volumes_l)


class PDParameters(Model):
    model: Literal["emax", "linear", "indirect_inhibition", "indirect_stimulation"] = "emax"
    driver: Literal["plasma", "effect_site"] = "effect_site"
    baseline: Nonnegative = 0.0
    # Signed change from baseline for Emax/linear; indirect models require >=0.
    maximum_effect: Finite = 100.0
    ec50_mg_l: Positive = 2.0
    hill: Positive = 1.0
    slope_per_mg_l: Finite = 1.0
    effect_equilibration_h: Positive = 0.5
    turnover_rate_h: Positive = 0.2

    @model_validator(mode="after")
    def check_indirect(self):
        if self.model.startswith("indirect"):
            if self.baseline <= 0 or self.maximum_effect < 0:
                raise ValueError("Indirect response requires baseline > 0 and maximum_effect >= 0")
            if self.model == "indirect_inhibition" and self.maximum_effect > 1:
                raise ValueError("Indirect inhibition maximum_effect is a fraction in [0, 1]")
        return self


class Dose(Model):
    time_h: Nonnegative = 0.0
    amount_mg: Positive = 100.0
    route: Literal["oral", "iv_bolus", "iv_infusion"] = "oral"
    duration_h: Nonnegative = 0.0

    @model_validator(mode="after")
    def check_duration(self):
        if self.route == "iv_infusion" and self.duration_h <= 0:
            raise ValueError("An IV infusion requires a positive duration_h")
        if self.route != "iv_infusion" and self.duration_h != 0:
            raise ValueError("duration_h applies only to IV infusion")
        if not math.isfinite(self.time_h + self.duration_h):
            raise ValueError("Dose end time must be finite")
        return self


class Provenance(Model):
    kind: Literal["synthetic", "literature", "user_supplied"] = "synthetic"
    description: str = "Illustrative parameters; not calibrated to a real drug or population."
    references: tuple[str, ...] = ()
    population: str = "Unspecified synthetic subject"
    formulation: str = "Idealized first-order absorption"

    @model_validator(mode="after")
    def literature_needs_sources(self):
        if self.kind == "literature" and not self.references:
            raise ValueError("Literature parameters require source references")
        return self


class Scenario(Model):
    schema_version: Literal[1] = 1
    name: str = "Synthetic two-compartment oral scenario"
    pk: PKParameters = Field(default_factory=PKParameters)
    pd: PDParameters = Field(default_factory=PDParameters)
    doses: tuple[Dose, ...] = (Dose(),)
    end_h: Positive = 48.0
    samples: Annotated[int, Field(ge=2, le=20001, strict=True)] = 481
    provenance: Provenance = Field(default_factory=Provenance)

    @model_validator(mode="after")
    def doses_within_horizon(self):
        for dose in self.doses:
            if dose.time_h > self.end_h:
                raise ValueError("Dose administration time exceeds the simulation horizon")
            if not math.isfinite(dose.time_h + self.pk.absorption_lag_h):
                raise ValueError("Absorption start time must be finite")
        return self


def repeated_doses(
    amount_mg: float,
    interval_h: float,
    count: int,
    *,
    start_h: float = 0.0,
    route: Literal["oral", "iv_bolus", "iv_infusion"] = "oral",
    duration_h: float = 0.0,
) -> tuple[Dose, ...]:
    """Explicit events: omit individual events to represent missed doses."""
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 10000:
        raise ValueError("count must be an integer between 1 and 10000")
    if not math.isfinite(interval_h) or interval_h <= 0:
        raise ValueError("interval_h must be finite and positive")
    return tuple(
        Dose(
            time_h=start_h + i * interval_h, amount_mg=amount_mg, route=route, duration_h=duration_h
        )
        for i in range(count)
    )

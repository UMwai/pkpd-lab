"""Lab → subjects → compartments, processes, and explicit custom equations."""

import keyword
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from .expressions import FUNCTIONS, unit_dimension
from .models import Finite, Model, Nonnegative, Positive

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,39}$")]
ObjectId = Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]


class Compartment(Model):
    symbol: Identifier
    name: Annotated[str, Field(min_length=1, max_length=100)]
    volume_l: Positive = 20
    initial_mg: Nonnegative = 0


class KineticProcess(Model):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    source: Identifier
    target: Identifier | None = None  # None means elimination from this subject.
    kinetic_order: Literal[0, 1, 2, 3] = 1
    coefficient: Nonnegative = 4

    @property
    def coefficient_unit(self):
        return ("mg/h", "L/h", "L^2/(mg*h)", "L^3/(mg^2*h)")[self.kinetic_order]


class Parameter(Model):
    symbol: Identifier
    value: Finite
    unit: str = "1"

    @field_validator("unit")
    @classmethod
    def check_unit(cls, value):
        unit_dimension(value)
        return value


class Equation(Model):
    symbol: Identifier
    derivative_order: Literal[0, 1, 2, 3] = 1
    rhs: Annotated[str, Field(min_length=1, max_length=512)]
    unit: str = "response"
    initial: tuple[Finite, ...] = (0.0,)

    @field_validator("unit")
    @classmethod
    def check_unit(cls, value):
        unit_dimension(value)
        return value

    @model_validator(mode="after")
    def initial_conditions(self):
        if len(self.initial) != self.derivative_order:
            raise ValueError(
                "An order-n equation needs n initial values; algebraic order 0 needs none"
            )
        return self


class LabDose(Model):
    time_h: Nonnegative = 0
    target: Identifier
    amount_mg: Positive = 100


class Subject(Model):
    id: ObjectId = Field(default_factory=lambda: uuid4().hex)
    name: Annotated[str, Field(min_length=1, max_length=100)] = "Body 1"
    notes: Annotated[str, Field(max_length=2000)] = "Synthetic research subject"
    compartments: Annotated[tuple[Compartment, ...], Field(max_length=12)] = ()
    processes: Annotated[tuple[KineticProcess, ...], Field(max_length=40)] = ()
    parameters: Annotated[tuple[Parameter, ...], Field(max_length=30)] = ()
    equations: Annotated[tuple[Equation, ...], Field(max_length=20)] = ()
    doses: Annotated[tuple[LabDose, ...], Field(max_length=500)] = ()

    @model_validator(mode="after")
    def consistent_symbols_and_links(self):
        symbols = [p.symbol for p in self.parameters]
        for c in self.compartments:
            symbols.extend((c.symbol, f"{c.symbol}_C"))
        for e in self.equations:
            symbols.append(e.symbol)
            symbols.extend(f"{e.symbol}_d{i}" for i in range(1, e.derivative_order))
        if len(set(symbols)) != len(symbols):
            raise ValueError(
                "All parameter, compartment, equation, and derivative symbols must be unique"
            )
        reserved = {
            "t",
            "time_h",
            "eliminated_mg",
            "initial_plus_dosed_mg",
            "mass_balance_error_mg",
        }
        if any(s in reserved or s in FUNCTIONS or keyword.iskeyword(s) for s in symbols):
            raise ValueError(
                "Time, ledger column names, function names, and Python keywords are reserved"
            )
        names = {c.symbol for c in self.compartments}
        for process in self.processes:
            if process.source not in names or (
                process.target is not None and process.target not in names
            ):
                raise ValueError("Every process must reference compartments in the same subject")
            if process.source == process.target:
                raise ValueError("A process cannot transfer to its own source")
        self.zero_source_order()  # Verify that empty-source flow constraints can be resolved.
        if any(d.target not in names for d in self.doses):
            raise ValueError("Every dose must target a compartment in the same subject")
        return self

    def zero_source_order(self):
        remaining = {p.source for p in self.processes if p.kinetic_order == 0 and p.coefficient > 0}
        order = []
        while remaining:
            incoming = {
                p.target
                for p in self.processes
                if p.source in remaining and p.target in remaining and p.coefficient > 0
            }
            ready = sorted(remaining - incoming)
            if not ready:
                raise ValueError("Cycles between zero-order source compartments are not supported")
            order.extend(ready)
            remaining.difference_update(ready)
        return order


class Lab(Model):
    kind: Literal["lab"] = "lab"
    lab_schema_version: Literal[1] = 1
    id: ObjectId = Field(default_factory=lambda: uuid4().hex)
    name: Annotated[str, Field(min_length=1, max_length=100)] = "Untitled lab"
    description: Annotated[str, Field(max_length=4000)] = "Synthetic research experiment"
    subjects: Annotated[tuple[Subject, ...], Field(max_length=12)] = ()
    end_h: Annotated[float, Field(gt=0, le=10000, allow_inf_nan=False)] = 48
    samples: Annotated[int, Field(ge=2, le=10001, strict=True)] = 481

    @model_validator(mode="after")
    def valid_subjects_and_doses(self):
        if len({s.id for s in self.subjects}) != len(self.subjects):
            raise ValueError("Subject IDs must be unique within a lab")
        if any(d.time_h > self.end_h for s in self.subjects for d in s.doses):
            raise ValueError("Dose time exceeds the lab simulation horizon")
        return self

"""Run a versioned JSON scenario and save data plus reproducibility metadata."""

import argparse
import hashlib
import json
from importlib.metadata import version
from pathlib import Path

from .models import Scenario
from .simulation import simulate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--output", type=Path, default=Path("outputs/simulation.csv"))
    args = parser.parse_args()
    scenario = Scenario.model_validate_json(args.scenario.read_text())
    result = simulate(scenario)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.frame.to_csv(args.output, index=False)
    canonical = scenario.model_dump_json()
    metadata = {
        "scenario": scenario.model_dump(mode="json"),
        "scenario_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "versions": {name: version(name) for name in ("pkpd-lab", "numpy", "scipy", "pydantic")},
        "solver": {"method": "LSODA", "rtol": 1e-8, "atol": 1e-10},
        "summary": result.summary(),
    }
    args.output.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(result.summary(), indent=2))


if __name__ == "__main__":
    main()

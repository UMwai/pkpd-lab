"""Generate or run a lab JSON file independently of the UI."""

import argparse
import json
from pathlib import Path

from .lab_engine import export_run, generate_lab, simulate_lab
from .lab_models import Lab


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["generate", "run"])
    parser.add_argument("lab", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    extension = ".json" if args.action == "generate" else ".zip"
    if args.output.suffix != extension:
        parser.error(f"{args.action} requires a {extension} output path")
    if args.output.exists():
        parser.error("Output already exists; choose a new path")
    try:
        if args.lab.stat().st_size > 2_000_000:
            raise ValueError("Lab imports are limited to 2 MB")
        lab = Lab.model_validate_json(args.lab.read_text())
        payload = (
            (json.dumps(generate_lab(lab), indent=2) + "\n").encode()
            if args.action == "generate"
            else export_run(lab, simulate_lab(lab))
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as output:
            output.write(payload)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"{args.action}: {len(lab.subjects)} subjects → {args.output}")


if __name__ == "__main__":
    main()

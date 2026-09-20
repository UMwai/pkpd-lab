"""Explicit local saves: JSON only, fixed IDs, atomic replacement, no repo data."""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from .lab_models import Lab


def lab_directory():
    return Path(os.environ.get("PKPD_LAB_DATA_DIR", Path.home() / ".local/share/pkpd-lab/labs"))


def save_lab(lab: Lab, directory: Path | None = None) -> Path:
    directory = directory or lab_directory()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{lab.id}.json"
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=directory, prefix=".lab-", suffix=".tmp", delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(lab.model_dump_json(indent=2) + "\n")
    try:
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def saved_labs(directory: Path | None = None) -> tuple[list[Lab], list[str]]:
    directory = directory or lab_directory()
    labs, errors = [], []
    for path in sorted(directory.glob("*.json")):
        try:
            if path.stat().st_size > 2_000_000:
                raise ValueError("File exceeds the 2 MB import limit")
            lab = Lab.model_validate_json(path.read_text())
            if path.stem != lab.id:
                raise ValueError("Filename and lab ID differ")
            labs.append(lab)
        except (ValueError, OSError) as exc:
            errors.append(f"{path.name}: {exc}")
    return labs, errors

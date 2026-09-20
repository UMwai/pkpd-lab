import json
import subprocess
import sys
import zipfile

from pkpd_lab.lab_templates import example_lab


def test_generate_and_run_commands_and_overwrite_rejection(tmp_path):
    source = tmp_path / "lab.json"
    source.write_text(example_lab().model_dump_json())
    generated = tmp_path / "model.json"
    bundle = tmp_path / "run.zip"
    for action, path in (("generate", generated), ("run", bundle)):
        subprocess.run(
            [sys.executable, "-m", "pkpd_lab.lab_cli", action, str(source), "--output", str(path)],
            check=True,
            capture_output=True,
        )
    assert len(json.loads(generated.read_text())["subjects"]) == 2
    with zipfile.ZipFile(bundle) as archive:
        assert "manifest.json" in archive.namelist()
        assert "lab.json" in archive.namelist()
    before = bundle.read_bytes()
    failed = subprocess.run(
        [sys.executable, "-m", "pkpd_lab.lab_cli", "run", str(source), "--output", str(bundle)],
        capture_output=True,
    )
    assert failed.returncode != 0 and b"already exists" in failed.stderr
    assert bundle.read_bytes() == before

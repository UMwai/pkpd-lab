import json
import subprocess
import sys

import pandas as pd

from pkpd_lab import Scenario


def test_cli_writes_trajectory_and_reproducibility_receipt(tmp_path):
    source = tmp_path / "scenario.json"
    output = tmp_path / "result.csv"
    source.write_text(Scenario().model_dump_json())
    subprocess.run(
        [sys.executable, "-m", "pkpd_lab.cli", str(source), "--output", str(output)],
        check=True,
        capture_output=True,
    )
    frame = pd.read_csv(output)
    metadata = json.loads(output.with_suffix(".json").read_text())
    assert len(frame) == 481
    assert len(metadata["scenario_sha256"]) == 64
    assert metadata["scenario"]["provenance"]["kind"] == "synthetic"
    assert metadata["summary"]["auc_0_end_mg_h_l"] == frame.auc_mg_h_l.iloc[-1]

"""Run real checks only after all CPU measurements finish, then integrated ablation."""

import json
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
deadline = time.monotonic() + 3600
while True:
    path = root / "artifacts/experiment-progress.json"
    status = json.loads(path.read_text()) if path.exists() else {}
    if status.get("status") == "completed":
        break
    if status.get("status") == "failed":
        raise SystemExit("Experiments failed; investigate before validation")
    if time.monotonic() > deadline:
        raise SystemExit("Experiment pipeline did not finish in time")
    time.sleep(1)
for name, args, env in [
    (
        "integrated-tests",
        [sys.executable, "-m", "pytest", "-q"],
        {"LATTICE_INTEGRATION": "1"},
    ),
    (
        "adaptive-session-1",
        [
            sys.executable,
            "experiments/adaptive_cpu.py",
            "--output",
            "benchmarks/results/adaptive-session-1",
            "--trials",
            "30",
        ],
        {},
    ),
]:
    import os

    with (root / "artifacts" / f"{name}.txt").open("w") as logs:
        result = subprocess.run(
            args,
            cwd=root,
            env=dict(os.environ, **env),
            stdout=logs,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if result.returncode:
        (root / "artifacts/finalize-progress.json").write_text(
            json.dumps(
                {"status": "failed", "job": name, "exit_code": result.returncode}
            )
            + "\n"
        )
        raise SystemExit(name + " failed")
(root / "artifacts/finalize-progress.json").write_text(
    json.dumps({"status": "completed"}) + "\n"
)

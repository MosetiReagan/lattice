"""Serialize three fixed-source CPU serving sessions, never overlapping arms."""

import json
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / ".local/frozen-batching"
for session in (1, 2, 3):
    name = f"batching-session-{session}"
    status = {"status": "running", "job": name}
    (root / "artifacts/batching-progress.json").write_text(json.dumps(status) + "\n")
    env = dict(
        os.environ,
        PYTHONPATH=str(source / "src"),
        LATTICE_CONFIG=str(root / "configs/batching-experiments.json"),
    )
    args = [
        sys.executable,
        str(source / "experiments/serving/benchmark.py"),
        "--output",
        f"benchmarks/results/{name}",
        "--trials",
        "30",
    ]
    if session == 1:
        args.append("--quality")
    with (root / "artifacts" / f"{name}.txt").open("w") as out:
        result = subprocess.run(
            args, cwd=root, env=env, stdout=out, stderr=subprocess.STDOUT, check=False
        )
    if result.returncode:
        status.update(status="failed", exit_code=result.returncode)
        (root / "artifacts/batching-progress.json").write_text(
            json.dumps(status) + "\n"
        )
        raise SystemExit(name + " failed; later sessions not launched")
(root / "artifacts/batching-progress.json").write_text(
    json.dumps({"status": "completed", "sessions": 3}) + "\n"
)

"""Serialize long CPU experiments; never benchmark two workers concurrently."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
# The existing precision job must finish before any further model work.
deadline = time.monotonic() + 1800
while not (root / "benchmarks/results/precision-session-1/summary.json").exists():
    if time.monotonic() > deadline:
        raise SystemExit("Precision run did not complete; subsequent jobs not started")
    time.sleep(1)
jobs = []
for session in (2, 3):
    jobs.append(
        (
            "cache-session-" + str(session),
            ".local/frozen-experiments/src",
            [
                ".local/frozen-experiments/experiments/cache_cpu.py",
                "--output",
                f"benchmarks/results/cache-session-{session}",
                "--trials",
                "30",
            ],
        )
    )
for session in (2, 3):
    jobs.append(
        (
            "standard-session-" + str(session),
            ".local/frozen-standard/src",
            [
                "scripts/run_baseline.py",
                "--config",
                "configs/frozen-baseline.json",
                "--output",
                f"benchmarks/results/standard-session-{session}",
            ],
        )
    )
jobs.append(
    (
        "speculative-session-1",
        ".local/frozen-experiments/src",
        [
            ".local/frozen-experiments/experiments/speculative_blocks.py",
            "--output",
            "benchmarks/results/speculative-session-1",
            "--trials",
            "30",
        ],
    )
)
for name, source, args in jobs:
    if (root / "benchmarks/results" / name / "summary.json").exists():
        continue
    env = dict(
        os.environ,
        PYTHONPATH=str(root / source),
        LATTICE_CONFIG=str(root / "configs/experiments-frozen.json"),
    )
    status = {"job": name, "status": "running", "source_root": source}
    (root / "artifacts/experiment-progress.json").write_text(
        json.dumps(status, indent=2) + "\n"
    )
    with (root / "artifacts" / f"{name}.txt").open("w") as logs:
        result = subprocess.run(
            [sys.executable, *args],
            cwd=root,
            env=env,
            stdout=logs,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if result.returncode:
        status.update(status="failed", exit_code=result.returncode)
        (root / "artifacts/experiment-progress.json").write_text(
            json.dumps(status, indent=2) + "\n"
        )
        raise SystemExit(f"{name} failed; later jobs not launched")
(root / "artifacts/experiment-progress.json").write_text(
    json.dumps({"status": "completed", "jobs": [j[0] for j in jobs]}, indent=2) + "\n"
)

"""Serialize analysis, boundary measurements, real tests and packaging."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


async def main(protocol_path=None):
    protocol_path = ROOT / (
        protocol_path or "benchmarks/workloads/chat-burst-confirmation-v1.json"
    )
    if not protocol_path.exists():
        raise SystemExit("No frozen confirmation protocol; no finalization was started")
    protocol = json.loads(protocol_path.read_text())
    if protocol.get("stage") != "frozen":
        raise SystemExit("Do not finalize an unexecuted draft as benchmark evidence")
    status_path = (
        ROOT
        / protocol.get("results_path", "benchmarks/results/chat-burst-confirmation-v1")
        / "orchestration.json"
    )
    while True:
        if status_path.exists():
            status = json.loads(status_path.read_text())["status"]
            if status == "failed":
                raise SystemExit(
                    "Confirmation execution failed; preserve all partial data"
                )
            if status == "completed":
                break
        await asyncio.sleep(5)
    arguments = ["--protocol", str(protocol_path)]
    boundary_command = [
        sys.executable,
        "experiments/chat_admission_boundaries.py",
        *arguments,
    ]
    if protocol.get("cpu_bandwidth"):
        budget = protocol["cpu_bandwidth"]
        boundary_command = [
            "sudo",
            "-n",
            sys.executable,
            "scripts/run_cpu_budget.py",
            "--group",
            budget["path"].lstrip("/"),
            "--quota-us",
            budget["cpu_max"].split()[0],
            "--cpu",
            str(protocol["cpu_affinity"][0]),
            "--settings",
            str(ROOT / protocol["settings_path"]),
            "--",
            *boundary_command,
        ]
    else:
        boundary_command = [
            "taskset",
            "-c",
            ",".join(str(cpu) for cpu in protocol["cpu_affinity"]),
            *boundary_command,
        ]
    prefix = protocol.get("artifact_prefix", "chat")
    build_path = protocol.get(
        "build_path", f".local/{prefix.rstrip('-')}-admission-build"
    )
    steps = [
        (
            "chat-confirmation-analysis.txt",
            [sys.executable, "scripts/analyze_chat_admission.py", *arguments],
        ),
        (
            "chat-boundaries.txt",
            boundary_command,
        ),
        (
            "chat-boundary-analysis.txt",
            [sys.executable, "scripts/analyze_chat_boundaries.py", *arguments],
        ),
        (
            "chat-final-lint.txt",
            [".venv/bin/ruff", "check", "src", "tests", "scripts", "experiments"],
        ),
        (
            "chat-final-format.txt",
            [
                ".venv/bin/ruff",
                "format",
                "--check",
                "src",
                "tests",
                "scripts",
                "experiments",
            ],
        ),
        ("chat-final-tests.txt", [sys.executable, "-m", "pytest", "-q"]),
        (
            "chat-final-build.txt",
            ["uv", "build", "--offline", "--out-dir", build_path],
        ),
    ]
    for name, command in steps:
        name = prefix + name.removeprefix("chat").removeprefix("-")
        with (ROOT / "artifacts" / name).open("x") as output:
            code = subprocess.run(  # noqa: ASYNC221 — no overlapping benchmark/model jobs
                command,
                cwd=ROOT,
                env={
                    **os.environ,
                    "LATTICE_INTEGRATION": "1",
                    "LATTICE_CONFIG": str(ROOT / protocol["settings_path"]),
                },
                stdout=output,
                stderr=subprocess.STDOUT,
                check=False,
            ).returncode
        if code:
            raise SystemExit("Finalization failed: " + name)
    print("Chat confirmation, boundaries, lint, real CPU tests and build completed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol")
    asyncio.run(main(parser.parse_args().protocol))

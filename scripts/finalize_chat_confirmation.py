"""Serialize analysis, boundary measurements, real tests and packaging."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


async def main():
    protocol_path = ROOT / "benchmarks/workloads/chat-burst-confirmation-v1.json"
    if not protocol_path.exists():
        raise SystemExit("No frozen confirmation protocol; no finalization was started")
    protocol = json.loads(protocol_path.read_text())
    if protocol.get("stage") != "frozen":
        raise SystemExit("Do not finalize an unexecuted draft as benchmark evidence")
    status_path = (
        ROOT / "benchmarks/results/chat-burst-confirmation-v1/orchestration.json"
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
    steps = [
        (
            "chat-confirmation-analysis.txt",
            [sys.executable, "scripts/analyze_chat_admission.py"],
        ),
        (
            "chat-boundaries.txt",
            [
                "taskset",
                "-c",
                ",".join(str(cpu) for cpu in protocol["cpu_affinity"]),
                sys.executable,
                "experiments/chat_admission_boundaries.py",
            ],
        ),
        (
            "chat-boundary-analysis.txt",
            [sys.executable, "scripts/analyze_chat_boundaries.py"],
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
            ["uv", "build", "--offline", "--out-dir", ".local/chat-admission-build"],
        ),
    ]
    for name, command in steps:
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
    asyncio.run(main())

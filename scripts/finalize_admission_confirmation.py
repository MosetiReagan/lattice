"""Sequence confirmation analysis, boundary diagnostics, tests and packaging."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


async def main():
    path = (
        ROOT / "benchmarks/results/burst-coalescing-confirmation-v1/orchestration.json"
    )
    while True:
        status = json.loads(path.read_text())
        if status["status"] == "failed":
            raise SystemExit("Confirmation execution failed; no success claim")
        if status["status"] == "completed":
            break
        await asyncio.sleep(5)
    steps = [
        (
            "admission-confirmation-analysis.txt",
            [sys.executable, "scripts/analyze_admission_confirmation.py"],
        ),
        (
            "admission-boundaries.txt",
            [sys.executable, "experiments/admission_boundaries.py"],
        ),
        ("admission-final-tests.txt", [sys.executable, "-m", "pytest", "-q"]),
    ]
    for name, command in steps:
        with (ROOT / "artifacts" / name).open("w") as output:
            code = subprocess.run(  # noqa: ASYNC221 — deliberately serialized after confirmation
                command,
                cwd=ROOT,
                env={**os.environ, "LATTICE_INTEGRATION": "1"},
                stdout=output,
                stderr=subprocess.STDOUT,
                check=False,
            ).returncode
        if code:
            raise SystemExit("Final check failed: " + name)
    print("Confirmation analysis, boundaries and full tests completed")


if __name__ == "__main__":
    asyncio.run(main())

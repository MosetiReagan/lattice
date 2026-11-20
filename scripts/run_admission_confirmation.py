"""Execute the fixed three-session admission confirmation without overlapping arms."""

import json
import subprocess
import sys
from pathlib import Path

from lattice.config import file_hash

ROOT = Path(__file__).resolve().parents[1]


def main():
    protocol_path = ROOT / "benchmarks/workloads/burst-coalescing-confirmation-v1.json"
    protocol = json.loads(protocol_path.read_text())
    root = ROOT / "benchmarks/results/burst-coalescing-confirmation-v1"
    root.mkdir(parents=True, exist_ok=False)
    status = {
        "protocol_sha256": file_hash(protocol_path),
        "sessions": [],
        "status": "running",
    }
    path = root / "orchestration.json"
    path.write_text(json.dumps(status, indent=2) + "\n")
    for index, session in enumerate(protocol["sessions"], start=1):
        output = root / f"session-{index}"
        command = [
            sys.executable,
            str(ROOT / "experiments/burst_admission.py"),
            "--output",
            str(output),
            "--seed",
            str(session["seed"]),
            "--traces",
            str(session["traces"]),
            "--arms",
            *protocol["baselines"],
            protocol["candidate"],
        ]
        with (root / f"session-{index}.log").open("w") as log:
            code = subprocess.run(
                command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False
            ).returncode
        status["sessions"].append(
            {
                "session": index,
                "seed": session["seed"],
                "exit_code": code,
                "summary_exists": (output / "summary.json").exists(),
            }
        )
        path.write_text(json.dumps(status, indent=2) + "\n")
        if code:
            status["status"] = "failed"
            path.write_text(json.dumps(status, indent=2) + "\n")
            raise SystemExit(
                "Confirmation failed; preserve partial results, do not replace or exclude"
            )
    status["status"] = "completed"
    path.write_text(json.dumps(status, indent=2) + "\n")
    print("Completed three fixed confirmation sessions")


if __name__ == "__main__":
    main()

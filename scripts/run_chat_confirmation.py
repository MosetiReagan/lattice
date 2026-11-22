"""Run the separately frozen chat protocol once, serially, without overwrites."""

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

from lattice.config import file_hash
from lattice.evaluation.benchmark import source_manifest
from lattice.observability.host import cpu_bandwidth_snapshot

ROOT = Path(__file__).resolve().parents[1]


def main(protocol_path=None):
    protocol_path = ROOT / (
        protocol_path or "benchmarks/workloads/chat-burst-confirmation-v1.json"
    )
    if not protocol_path.exists():
        raise SystemExit(
            "No frozen chat protocol: resolve CPU availability and finish development before confirmation"
        )
    protocol = json.loads(protocol_path.read_text())
    if protocol.get("stage") != "frozen":
        raise SystemExit(
            "Confirmation requires a reviewed frozen protocol, not a draft"
        )
    os.environ["LATTICE_CONFIG"] = str(ROOT / protocol["settings_path"])
    if file_hash(ROOT / protocol["settings_path"]) != protocol["settings_sha256"]:
        raise SystemExit("Frozen settings changed")
    os.sched_setaffinity(0, set(protocol["cpu_affinity"]))
    required_budget = protocol.get("cpu_bandwidth")
    if required_budget and any(
        cpu_bandwidth_snapshot().get(key) != value
        for key, value in required_budget.items()
    ):
        raise SystemExit("Execution must use the exact frozen cgroup CPU budget")
    preflight = json.loads((ROOT / protocol["host_preflight_path"]).read_text())
    if (
        protocol.get("host_preflight_sha256")
        and preflight.get("checker_sha256") != protocol["host_preflight_sha256"]
    ):
        raise SystemExit("Preflight checker differs from frozen protocol")
    if (
        preflight.get("workers") != protocol["threads"]
        or preflight.get("cpu_affinity") != protocol["cpu_affinity"]
    ):
        raise SystemExit(
            "Preflight must match the frozen thread budget and CPU affinity"
        )
    if not preflight["eligible"]:
        raise SystemExit(
            "Host CPU preflight failed; do not start fixed confirmation budget"
        )
    if required_budget and any(
        preflight.get("cpu_bandwidth", {}).get(key) != value
        for key, value in required_budget.items()
    ):
        raise SystemExit("Preflight CPU budget differs from frozen execution")
    age = (
        datetime.datetime.now(datetime.UTC)
        - datetime.datetime.fromisoformat(preflight["utc"])
    ).total_seconds()
    if not 0 <= age <= 120:
        raise SystemExit(
            "Host preflight is stale; a fresh eligibility check is required"
        )
    protocol_hash = file_hash(protocol_path)
    output = ROOT / protocol.get(
        "results_path", "benchmarks/results/chat-burst-confirmation-v1"
    )
    output.mkdir(parents=True, exist_ok=False)
    path = output / "orchestration.json"
    state = {"status": "running", "protocol_sha256": protocol_hash, "sessions": []}
    path.write_text(json.dumps(state, indent=2) + "\n")
    for index, spec in enumerate(protocol["sessions"], 1):
        if (
            file_hash(protocol_path) != protocol_hash
            or source_manifest()["sha256"] != protocol["source_sha256"]
            or file_hash(ROOT / protocol["settings_path"])
            != protocol["settings_sha256"]
            or sorted(os.sched_getaffinity(0)) != protocol["cpu_affinity"]
            or (
                required_budget
                and any(
                    cpu_bandwidth_snapshot().get(key) != value
                    for key, value in required_budget.items()
                )
            )
        ):
            state["status"] = "failed"
            path.write_text(json.dumps(state, indent=2) + "\n")
            raise SystemExit("Frozen source/protocol changed; preserve partial run")
        command = [
            sys.executable,
            "experiments/chat_burst_admission.py",
            "--output",
            str(output / f"session-{index}"),
            "--seed",
            str(spec["seed"]),
            "--traces",
            str(spec["traces"]),
            "--arms",
            *protocol["baselines"],
            protocol["candidate"],
        ]
        with (output / f"session-{index}.log").open("x") as log:
            code = subprocess.run(
                command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False
            ).returncode
        state["sessions"].append(
            {"session": index, "seed": spec["seed"], "exit_code": code}
        )
        if code:
            state["status"] = "failed"
            path.write_text(json.dumps(state, indent=2) + "\n")
            raise SystemExit("Session execution failed; do not replace failed data")
        path.write_text(json.dumps(state, indent=2) + "\n")
    state["status"] = "completed"
    path.write_text(json.dumps(state, indent=2) + "\n")
    print("All frozen chat confirmation sessions complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol")
    main(parser.parse_args().protocol)

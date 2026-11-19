"""Qualify only exact public prompts proven equivalent in three cache sessions.

Does not extrapolate cache equivalence to arbitrary prompts, models or sampling.
"""

import dataclasses
import hashlib
import json
import statistics
from pathlib import Path

from lattice.controller.policy import PathEvidence
from lattice.evaluation.benchmark import prompt_for
from lattice.observability.hardware import inventory_fingerprint

root = Path(__file__).resolve().parents[1]
sessions = [root / f"benchmarks/results/cache-session-{i}" for i in (1, 2, 3)]
records = []
manifests = []
for folder in sessions:
    manifests.append(json.loads((folder / "manifest.json").read_text()))
    rows = [
        json.loads(line)
        for line in (folder / "requests.jsonl").read_text().splitlines()
    ]
    for workload in manifests[-1]["workloads"]:
        for trial in range(30):
            pair = {
                r["arm"]: r
                for r in rows
                if r["trial"] == trial and r["workload"] == workload["id"]
            }
            if (
                set(pair) != {"standard", "cached"}
                or pair["standard"]["token_ids"] != pair["cached"]["token_ids"]
            ):
                raise SystemExit("Missing or unequal output pair; evidence rejected")
    records.extend(rows)
if len({m["model_sha256"] for m in manifests}) != 1:
    raise SystemExit("Model changed across sessions")
hardware = inventory_fingerprint(
    json.loads((root / "benchmarks/baseline/environment.json").read_text())
)
baseline_binary = json.loads((root / "benchmarks/baseline/manifest.json").read_text())[
    "backend_sha256"
]
for manifest, folder in zip(manifests, sessions, strict=True):
    if manifest.get("cpu_fingerprint"):
        if manifest["cpu_fingerprint"] != hardware or manifest.get("threads") != 4:
            raise SystemExit(
                "Hardware/thread scope differs; build separate profiles from that recorded inventory"
            )
    else:
        raw_rows = [
            json.loads(line)
            for line in (folder / "requests.jsonl").read_text().splitlines()
        ]
        if any(r["backend"]["binary_sha256"] != baseline_binary for r in raw_rows):
            raise SystemExit(
                "Legacy experiment lacks hardware scope and does not match archived build"
            )
profiles = []
for workload in manifests[0]["workloads"]:
    for arm in ["standard", "cached"]:
        rows = [
            r for r in records if r["workload"] == workload["id"] and r["arm"] == arm
        ]
        if len(rows) != 90:
            raise SystemExit("Need 30 trials per session, three sessions")
        model_sha = {r["backend"]["model_sha256"] for r in rows}
        backend_sha = {r["backend"]["binary_sha256"] for r in rows}
        if len(model_sha) != 1 or len(backend_sha) != 1:
            raise SystemExit("Artifact identity changed")
        hashes = frozenset(
            hashlib.sha256(prompt_for(workload, i).encode()).hexdigest()
            for i in range(30)
        )
        item = PathEvidence(
            arm,
            next(iter(model_sha)),
            next(iter(backend_sha)),
            min(r["prompt_tokens"] for r in rows),
            max(r["prompt_tokens"] for r in rows),
            16,
            statistics.median(r["total_ms"] for r in rows),
            4096,
            90,
            3,
            0,
            True,
            "cache-cpu-3sessions-v1",
            hashes,
            4,
            hardware,
        )
        row = dataclasses.asdict(item)
        row["qualified_prompt_sha256"] = sorted(row["qualified_prompt_sha256"])
        profiles.append(row)
result = {
    "policy_version": "rules-1",
    "scope": "Exact known public synthetic prompts only; not generalized task quality",
    "memory_bound_note": "Serving uses a 4096 MiB RLIMIT_AS cap, distinct from sampled RSS; integration must verify this cap.",
    "source_manifests": [
        {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (folder / "manifest.json", folder / "requests.jsonl")
        }
        for folder in sessions
    ],
    "profiles": profiles,
}
path = root / "configs/measured-policy.json"
path.write_text(json.dumps(result, indent=2) + "\n")
print(path)

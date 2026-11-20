"""Post-confirmation boundary checks; no tuning or replacement of frozen results."""

import asyncio
import json
from pathlib import Path

from burst_admission import make_trace, run_trace

from lattice.config import file_hash

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("interactive_only", 0, 12, 0.0),
    ("bulk_only", 6, 0, 0.0),
    ("mixed_25_percent_interactive", 9, 3, 0.03),
    ("mixed_75_percent_interactive", 3, 9, 0.03),
    ("interactive_arrives_late", 6, 6, 0.15),
]


async def main():
    root = ROOT / "benchmarks/results/burst-coalescing-boundaries-v1"
    root.mkdir(parents=True, exist_ok=False)
    manifest = {
        "stage": "Post-confirmation boundary diagnostics only. These cases do not replace the frozen primary workload or determine new policy parameters.",
        "cases": CASES,
        "arms": ["native8", "lattice_coalesce4"],
        "runner_sha256": file_hash(Path(__file__)),
        "trace_generator_sha256": file_hash(ROOT / "experiments/burst_admission.py"),
        "seed_start": 8001,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    results = []
    with (root / "results.jsonl").open("x") as stream:
        for index, (name, bulk, interactive, delay) in enumerate(CASES):
            trace = make_trace(8001 + index, bulk=bulk, interactive=interactive)
            for row in trace:
                if row["class"] == "interactive":
                    row["arrival_seconds"] = (
                        delay + (int(row["id"].split("-")[-1]) - bulk) * 0.002
                    )
            arms = (
                manifest["arms"] if index % 2 == 0 else list(reversed(manifest["arms"]))
            )
            for arm in arms:
                result = await run_trace(arm, trace, root)
                result["case"] = name
                results.append(result)
                stream.write(json.dumps(result) + "\n")
                stream.flush()
                print(
                    name,
                    arm,
                    "throughput",
                    result["tokens_per_second"],
                    "errors",
                    result["failures"],
                    flush=True,
                )
    # Additional high-concurrency native challengers: development seed only.
    # They do not alter or replace the locked primary confirmation.
    for arm in ["native16", "native32", "lattice_coalesce4"]:
        result = await run_trace(arm, make_trace(1002), root)
        result["case"] = "extra_native_slot_challengers_development_seed"
        results.append(result)
        with (root / "results.jsonl").open("a") as stream:
            stream.write(json.dumps(result) + "\n")
        print(
            result["case"],
            arm,
            "throughput",
            result["tokens_per_second"],
            "errors",
            result["failures"],
            flush=True,
        )
    (root / "summary.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main())

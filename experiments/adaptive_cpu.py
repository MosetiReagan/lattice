"""Live integrated policy ablation on held-back executions of qualified prompts."""

import argparse
import asyncio
import hashlib
import json
import random
from pathlib import Path

from lattice.backends.llama_cpp import LlamaCppBackend
from lattice.config import load_settings
from lattice.evaluation.benchmark import prompt_for, source_manifest
from lattice.observability.measure import export_csv, summarize
from lattice.runtime import Runtime
from lattice.types import GenerationRequest

p = argparse.ArgumentParser()
p.add_argument("--output", type=Path, required=True)
p.add_argument("--trials", type=int, default=30)
a = p.parse_args()


async def main():
    a.output.mkdir(parents=True, exist_ok=False)
    settings = load_settings()
    settings.log_directory = str(a.output / "private")
    backend = LlamaCppBackend(settings, settings.models[0])
    runtime = Runtime(settings, settings.models[0].id, backend)
    records = []
    rng = random.Random(9182)
    workloads = [
        {"id": "short", "input_words": 24, "output_tokens": 16},
        {"id": "long_prompt", "input_words": 900, "output_tokens": 16},
        {"id": "repeated_prefix", "input_words": 512, "output_tokens": 16},
    ]
    (a.output / "manifest.json").write_text(
        json.dumps(
            {
                "source": source_manifest(),
                "trials": a.trials,
                "scope": "New executions, known prompts; not held-out prompt generalization",
                "policy_sha256": hashlib.sha256(
                    Path(settings.policy_file).read_bytes()
                ).hexdigest(),
                "seed": 9182,
                "warmup": "One identical priming request per arm/trial, excluded symmetrically",
                "worker_address_space_mb": settings.worker_address_space_mb,
            },
            indent=2,
        )
        + "\n"
    )
    try:
        await backend.start()
        with (a.output / "requests.jsonl").open("x") as raw:
            for workload in workloads:
                for trial in range(a.trials):
                    arms = ["standard", "adaptive"]
                    rng.shuffle(arms)
                    pair = {}
                    for arm in arms:
                        request = GenerationRequest(
                            model=runtime.model_id,
                            prompt=prompt_for(workload, trial),
                            max_tokens=16,
                            optimization={"mode": arm},
                        )
                        await runtime.generate(request)
                        result = await runtime.generate(request)
                        row = dict(result["metadata"])
                        row.update(
                            arm=arm,
                            trial=trial,
                            workload=workload["id"],
                            token_ids=result["token_ids"],
                        )
                        pair[arm] = row
                        records.append(row)
                        raw.write(json.dumps(row) + "\n")
                        raw.flush()
                    if pair["standard"]["token_ids"] != pair["adaptive"]["token_ids"]:
                        raise RuntimeError("Adaptive output changed; policy rejected")
    finally:
        backend.stop()
    summary = {
        w["id"]: {
            arm: {
                "latency_ms": summarize(
                    [
                        r["total_ms"]
                        for r in records
                        if r["workload"] == w["id"] and r["arm"] == arm
                    ]
                ),
                "selected_paths": {
                    s: sum(
                        r["strategy"] == s
                        for r in records
                        if r["workload"] == w["id"] and r["arm"] == arm
                    )
                    for s in ["standard", "cached", "speculative"]
                },
            }
            for arm in ["standard", "adaptive"]
        }
        for w in workloads
    }
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    export_csv(records, a.output / "requests.csv")


asyncio.run(main())

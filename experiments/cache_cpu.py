"""Paired warmed-prefix ablation; warm-up cost is excluded symmetrically."""

import argparse
import asyncio
import hashlib
import json
import random
from pathlib import Path

from lattice.backends.llama_cpp import LlamaCppBackend
from lattice.config import load_settings
from lattice.evaluation.benchmark import prompt_for, source_manifest
from lattice.observability.hardware import cpu_fingerprint
from lattice.observability.measure import RssSampler, export_csv, summarize
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
    workloads = [
        {"id": "short", "input_words": 24, "output_tokens": 16},
        {"id": "long_prompt", "input_words": 900, "output_tokens": 16},
        {"id": "repeated_prefix", "input_words": 512, "output_tokens": 16},
    ]
    (a.output / "manifest.json").write_text(
        json.dumps(
            {
                "source": source_manifest(),
                "cpu_fingerprint": cpu_fingerprint(),
                "threads": settings.threads,
                "trials": a.trials,
                "model_sha256": settings.models[0].sha256,
                "seed": 1701,
                "workloads": workloads,
                "context_tokens": settings.context_tokens,
                "sampling": {"temperature": 0.0, "max_tokens": 16},
                "warmup": "One unmeasured identical prompt per arm/trial; both arms receive same warmups. Cold costs not an end-to-end win claim.",
            },
            indent=2,
        )
        + "\n"
    )
    records = []
    rng = random.Random(1701)
    try:
        await backend.start()
        with (a.output / "requests.jsonl").open("x") as raw:
            for workload in workloads:
                for trial in range(a.trials):
                    arms = ["standard", "cached"]
                    rng.shuffle(arms)
                    pair = {}
                    for arm in arms:
                        request = GenerationRequest(
                            model=runtime.model_id,
                            prompt=prompt_for(workload, trial),
                            max_tokens=16,
                            optimization={"mode": arm},
                            timeout_seconds=120.0,
                        )
                        await runtime.generate(request)
                        async with RssSampler(backend.process.pid) as memory:
                            result = await runtime.generate(request)
                        row = dict(result["metadata"])
                        row.update(
                            arm=arm,
                            trial=trial,
                            workload=workload["id"],
                            token_ids=result["token_ids"],
                            output_sha256=hashlib.sha256(
                                json.dumps(result["token_ids"]).encode()
                            ).hexdigest(),
                            sampled_worker_rss_peak_bytes=memory.peak_bytes,
                        )
                        pair[arm] = row
                        records.append(row)
                        raw.write(json.dumps(row) + "\n")
                        raw.flush()
                    if pair["standard"]["token_ids"] != pair["cached"]["token_ids"]:
                        (a.output / "quality-mismatch.json").write_text(
                            json.dumps(pair, indent=2) + "\n"
                        )
                        raise RuntimeError(
                            "Cache changed greedy token IDs; experiment rejected"
                        )
    finally:
        backend.stop()
    summary = {}
    for workload in workloads:
        summary[workload["id"]] = {
            arm: {
                "latency_ms": summarize(
                    [
                        r["total_ms"]
                        for r in records
                        if r["workload"] == workload["id"] and r["arm"] == arm
                    ]
                ),
                "reused_tokens": sum(
                    r.get("tokens_cached", 0)
                    for r in records
                    if r["workload"] == workload["id"] and r["arm"] == arm
                ),
            }
            for arm in ["standard", "cached"]
        }
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    export_csv(records, a.output / "requests.csv")


asyncio.run(main())

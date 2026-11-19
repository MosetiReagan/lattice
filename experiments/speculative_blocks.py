"""Bounded, block-randomized repeated native greedy speculation experiment."""

import argparse
import asyncio
import json
import random
from pathlib import Path

from lattice.backends.llama_cpp import LlamaCppBackend
from lattice.config import load_settings, select_model
from lattice.evaluation.benchmark import source_manifest
from lattice.observability.measure import RssSampler, export_csv, summarize
from lattice.runtime import Runtime
from lattice.types import GenerationRequest

p = argparse.ArgumentParser()
p.add_argument("--output", required=True, type=Path)
p.add_argument("--trials", type=int, default=30)
a = p.parse_args()


async def main():
    a.output.mkdir(parents=True, exist_ok=False)
    settings = load_settings()
    settings.draft_model_id = "qwen2.5-0.5b-instruct-f16"
    settings.context_tokens = 1024
    settings.log_directory = str(a.output / "private")
    target = select_model(settings, "qwen2.5-1.5b-instruct-q8")
    manifest = {
        "source": source_manifest(),
        "trials": a.trials,
        "warmups_per_block": 3,
        "seed": 1701,
        "target": target.model_dump(exclude={"path"}),
        "draft": settings.draft_model_id,
        "context_tokens": 1024,
        "max_output_tokens": 64,
        "temperature": 0,
        "design": "Randomized arm blocks per draft length; paired prompt/seed indices. One session, block-order confounding disclosed.",
    }
    (a.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    prompts = [
        "Explain why measurements should be repeated in a scientific experiment.",
        "Write a list of the first twenty positive integers.",
        "The main purpose of a computer memory cache is",
    ]
    records = []
    rng = random.Random(1701)
    with (a.output / "requests.jsonl").open("x") as raw:
        for length in (1, 2, 4, 8):
            arms = ["standard", "speculative"]
            rng.shuffle(arms)
            for arm in arms:
                backend = LlamaCppBackend(settings, target)
                runtime = Runtime(settings, target.id, backend)
                try:
                    for index in range(-3, a.trials):
                        request = GenerationRequest(
                            model=target.id,
                            prompt=prompts[index % 3],
                            max_tokens=64,
                            optimization={
                                "mode": arm,
                                "draft_tokens": length,
                                "allow_fallback": False,
                            },
                            timeout_seconds=120.0,
                        )
                        if index == -3:
                            await backend.configure(request)
                            await backend.start()
                        async with RssSampler(backend.process.pid) as memory:
                            result = await runtime.generate(request)
                        if index < 0:
                            continue
                        row = dict(result["metadata"])
                        row.update(
                            workload="speculative",
                            trial=index,
                            arm=arm,
                            draft_length=length,
                            token_ids=result["token_ids"],
                            sampled_worker_rss_peak_bytes=memory.peak_bytes,
                        )
                        records.append(row)
                        raw.write(json.dumps(row) + "\n")
                        raw.flush()
                finally:
                    backend.stop()
    mismatches = []
    summary = {}
    for length in (1, 2, 4, 8):
        group = [r for r in records if r["draft_length"] == length]
        for index in range(a.trials):
            pair = {r["arm"]: r for r in group if r["trial"] == index}
            if pair["standard"]["token_ids"] != pair["speculative"]["token_ids"]:
                mismatches.append({"draft_length": length, "trial": index})
        summary[str(length)] = {
            arm: {
                "latency_ms": summarize(
                    [r["total_ms"] for r in group if r["arm"] == arm]
                ),
                "draft_proposed": sum(
                    r["backend_timings"].get("draft_n", 0)
                    for r in group
                    if r["arm"] == arm
                ),
                "draft_accepted": sum(
                    r["backend_timings"].get("draft_n_accepted", 0)
                    for r in group
                    if r["arm"] == arm
                ),
                "rss_bytes": summarize(
                    [
                        r["sampled_worker_rss_peak_bytes"]
                        for r in group
                        if r["arm"] == arm
                    ]
                ),
            }
            for arm in ["standard", "speculative"]
        }
    summary["greedy_mismatches"] = mismatches
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    export_csv(records, a.output / "requests.csv")
    if mismatches:
        raise RuntimeError("Greedy mismatches prevent qualification")


asyncio.run(main())

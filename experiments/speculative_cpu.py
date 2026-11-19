"""Real greedy speculative ablation against the identical Q8 target artifact."""

import argparse
import asyncio
import hashlib
import json
import random
from pathlib import Path

from lattice.backends.llama_cpp import LlamaCppBackend
from lattice.config import load_settings, select_model
from lattice.evaluation.benchmark import source_manifest
from lattice.observability.measure import RssSampler, export_csv, summarize
from lattice.runtime import Runtime
from lattice.types import GenerationRequest

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--trials", type=int, default=30)
args = parser.parse_args()


async def main():
    settings = load_settings()
    settings.draft_model_id = "qwen2.5-0.5b-instruct-f16"
    settings.context_tokens = 1024
    settings.log_directory = str(args.output / "private")
    entry = select_model(settings, "qwen2.5-1.5b-instruct-q8")
    args.output.mkdir(parents=True, exist_ok=False)
    records = []
    warmup = 1
    spec = {
        "source": source_manifest(),
        "target": entry.model_dump(exclude={"path"}),
        "draft": select_model(settings, settings.draft_model_id).model_dump(
            exclude={"path"}
        ),
        "trials": args.trials,
        "warmups_per_arm": warmup,
        "seed": 1701,
        "context_tokens": 1024,
        "sampling": {"temperature": 0.0, "max_tokens": 64},
        "note": "Same Q8 target for both arms; does not compare Q8 quality against FP16.",
    }
    (args.output / "manifest.json").write_text(json.dumps(spec, indent=2) + "\n")
    # Each trial uses both paths; randomize which worker runs first.
    prompts = [
        "Explain why measurements should be repeated in a scientific experiment.",
        "Write a list of the first twenty positive integers.",
        "The main purpose of a computer memory cache is",
    ]
    rng = random.Random(1701)
    with (args.output / "requests.jsonl").open("x") as raw:
        for length in (1, 2, 4, 8):
            for trial in range(args.trials):
                arms = ["standard", "speculative"]
                rng.shuffle(arms)
                pair = {}
                for mode in arms:
                    backend = LlamaCppBackend(settings, entry)
                    request = GenerationRequest(
                        model=entry.id,
                        prompt=prompts[trial % len(prompts)],
                        max_tokens=64,
                        timeout_seconds=180.0,
                        optimization={
                            "mode": mode,
                            "draft_tokens": length,
                            "allow_fallback": False,
                        },
                    )
                    runtime = Runtime(settings, entry.id, backend)
                    try:
                        await backend.configure(request)
                        await backend.start()
                        for _ in range(warmup):
                            await runtime.generate(request)
                        async with RssSampler(backend.process.pid) as memory:
                            result = await runtime.generate(request)
                        item = dict(result["metadata"])
                        item.update(
                            workload="speculative",
                            trial=trial,
                            draft_length=length,
                            arm=mode,
                            output_sha256=hashlib.sha256(
                                json.dumps(result["token_ids"]).encode()
                            ).hexdigest(),
                            token_ids=result["token_ids"],
                            text=result["text"],
                            sampled_worker_rss_peak_bytes=memory.peak_bytes,
                        )
                        pair[mode] = item
                        records.append(item)
                        raw.write(json.dumps(item) + "\n")
                        raw.flush()
                    finally:
                        backend.stop()
                if pair["standard"]["token_ids"] != pair["speculative"]["token_ids"]:
                    (args.output / "quality-mismatch.json").write_text(
                        json.dumps(pair, indent=2) + "\n"
                    )
                    raise RuntimeError(
                        "Greedy token mismatch; experiment stopped rather than accepting quality loss"
                    )
    summary = {}
    for length in (1, 2, 4, 8):
        group = [r for r in records if r["draft_length"] == length]
        summary[str(length)] = {
            mode: {
                "latency_ms": summarize(
                    [r["total_ms"] for r in group if r["arm"] == mode]
                ),
                "draft_proposed": sum(
                    r["backend_timings"].get("draft_n", 0)
                    for r in group
                    if r["arm"] == mode
                ),
                "draft_accepted": sum(
                    r["backend_timings"].get("draft_n_accepted", 0)
                    for r in group
                    if r["arm"] == mode
                ),
                "rss_bytes": summarize(
                    [
                        r["sampled_worker_rss_peak_bytes"]
                        for r in group
                        if r["arm"] == mode
                    ]
                ),
            }
            for mode in ["standard", "speculative"]
        }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    export_csv(records, args.output / "requests.csv")


asyncio.run(main())

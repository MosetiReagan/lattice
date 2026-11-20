"""Separately versioned chat-framed study; never overwrites failed raw study."""

import argparse
import asyncio
import hashlib
import json
import os
import random
from pathlib import Path

import httpx
from burst_admission import MODEL, make_trace, run_trace

from lattice.backends.http_client import native_ssl_context
from lattice.backends.llama_cpp import LlamaCppBackend
from lattice.config import file_hash, load_settings, select_model
from lattice.evaluation.benchmark import source_manifest
from lattice.observability.host import CpuStealSampler

ROOT = Path(__file__).resolve().parents[1]


async def prepare_traces(seeds, output):
    """Use the model's actual template, identically for every arm, before timing."""
    settings = load_settings()
    settings.log_directory = str(output / "private" / "template-preparation")
    backend = LlamaCppBackend(settings, select_model(settings, MODEL))
    traces = [make_trace(seed) for seed in seeds]
    try:
        await backend.start()
        async with httpx.AsyncClient(
            base_url=backend.base_url,
            headers=backend.headers,
            verify=native_ssl_context(),
            trust_env=False,
            timeout=30.0,
        ) as client:
            for trace in traces:
                for row in trace:
                    original = row["prompt"]
                    response = await client.post(
                        "/apply-template",
                        json={"messages": [{"role": "user", "content": original}]},
                    )
                    response.raise_for_status()
                    row["prompt"] = response.json()["prompt"]
                    row["raw_prompt_sha256"] = row["prompt_sha256"]
                    row["prompt_sha256"] = hashlib.sha256(
                        row["prompt"].encode()
                    ).hexdigest()
    finally:
        backend.stop()
    return traces


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--traces", type=int, default=2)
    parser.add_argument("--arms", nargs="+", required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    seeds = list(range(args.seed, args.seed + args.traces))
    traces = await prepare_traces(seeds, args.output)
    settings = load_settings()
    manifest = {
        "seed": args.seed,
        "trace_count": args.traces,
        "traces": traces,
        "arms": args.arms,
        "source": source_manifest(),
        "settings_sha256": file_hash(
            Path(os.environ.get("LATTICE_CONFIG", "configs/local.json"))
        ),
        "cpu_affinity": sorted(os.sched_getaffinity(0))
        if hasattr(os, "sched_getaffinity")
        else None,
        "runner_sha256": file_hash(Path(__file__)),
        "transport_runner_sha256": file_hash(ROOT / "experiments/burst_admission.py"),
        "backend_sha256": settings.backend_sha256,
        "model_sha256": select_model(settings, MODEL).sha256,
        "worker_address_space_mb": settings.worker_address_space_mb,
        "context_per_request": settings.context_tokens,
        "threads": settings.threads,
        "protocol": "Separate chat-framed development study after the failed raw-prompt confirmation. Actual model /apply-template applied before timing to every source prompt. Identical rendered bytes/tokenizer/sampling/caps across arms. No exclusions or forced output lengths. This is not a reinterpretation of the original confirmation.",
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    rng = random.Random(args.seed)
    results = []
    with (args.output / "results.jsonl").open("x") as raw:
        for index, trace in enumerate(traces):
            arms = args.arms.copy()
            rng.shuffle(arms)
            for arm in arms:
                async with CpuStealSampler() as host_cpu:
                    result = await run_trace(arm, trace, args.output)
                result["host_cpu"] = host_cpu.summary()
                result["trace"] = index
                results.append(result)
                raw.write(json.dumps(result) + "\n")
                raw.flush()
                print(
                    arm,
                    index,
                    "P95",
                    result["summary"]["interactive"]["p95"],
                    "tps",
                    result["tokens_per_second"],
                    "errors",
                    result["failures"],
                    "correct",
                    sum(row.get("exact_correct", False) for row in result["rows"]),
                    flush=True,
                )
    (args.output / "summary.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main())

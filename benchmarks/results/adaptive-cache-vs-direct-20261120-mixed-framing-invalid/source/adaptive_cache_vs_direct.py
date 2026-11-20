"""Compare exact-scope adaptive prefix reuse with direct native llama.cpp caching."""

import argparse
import asyncio
import datetime
import hashlib
import json
import random
import time
from pathlib import Path

import httpx

from lattice.backends import create_backend
from lattice.config import file_hash, load_settings, select_model
from lattice.evaluation.benchmark import prompt_for, source_manifest
from lattice.observability.measure import RssSampler, summarize
from lattice.runtime import Runtime
from lattice.types import GenerationRequest, Optimization

ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen2.5-0.5b-instruct-f16"
WORKLOAD = {
    "id": "repeated_prefix",
    "kind": "serial",
    "input_words": 512,
    "output_tokens": 16,
}
ARMS = ["direct_uncached", "direct_native_cache", "lattice_adaptive"]


async def direct_request(backend, prompt, cache_prompt):
    started = time.perf_counter()
    async with httpx.AsyncClient(
        base_url=backend.base_url,
        headers=backend.headers,
        timeout=None,
        trust_env=False,
    ) as client:
        template = await backend._post(
            client,
            "/apply-template",
            {"messages": [{"role": "user", "content": prompt}]},
        )
        tokenized = await backend._post(
            client,
            "/tokenize",
            {"content": template["prompt"], "add_special": True, "parse_special": True},
        )
        prompt_ids = tokenized["tokens"]
        if len(prompt_ids) + 16 > backend.settings.context_tokens:
            raise ValueError("Prompt exceeds configured context")
        body = {
            "prompt": prompt_ids,
            "n_predict": 16,
            "stream": True,
            "temperature": 0.0,
            "seed": 84721,
            "top_k": 0,
            "top_p": 1.0,
            "min_p": 0.0,
            "repeat_penalty": 1.0,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "samplers": ["temperature"],
            "cache_prompt": cache_prompt,
            "return_tokens": True,
        }
        chunks, token_ids, timings = [], [], None
        async with client.stream("POST", "/completion", json=body) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                item = json.loads(line[6:])
                if "error" in item:
                    raise RuntimeError("Direct native generation failed")
                if item.get("stop"):
                    timings = item.get("timings", {})
                    break
                tokens = item.get("tokens", [])
                if len(token_ids) + len(tokens) > 16:
                    raise RuntimeError("Direct arm exceeded output cap")
                token_ids.extend(tokens)
                chunks.append(item.get("content", ""))
        if timings is None:
            raise RuntimeError("Missing native terminal event")
    return {
        "text": "".join(chunks),
        "token_ids": token_ids,
        "prompt_tokens": len(prompt_ids),
        "completion_tokens": len(token_ids),
        "tokens_cached": timings.get("cache_n", 0),
        "native_timings": timings,
        "elapsed_ms": (time.perf_counter() - started) * 1000,
        "selected_strategy": "direct_native_cache"
        if cache_prompt
        else "direct_uncached",
    }


async def lattice_request(runtime, prompt):
    result = await runtime.generate(
        GenerationRequest(
            model=MODEL,
            prompt=prompt,
            max_tokens=16,
            temperature=0.0,
            seed=84721,
            timeout_seconds=120.0,
            optimization=Optimization(mode="adaptive", profile="balanced"),
        )
    )
    record = result["metadata"]
    return {
        "text": result["text"],
        "token_ids": result["token_ids"],
        "prompt_tokens": record["prompt_tokens"],
        "completion_tokens": record["completion_tokens"],
        "tokens_cached": record.get("tokens_cached", 0),
        "native_timings": record.get("backend_timings"),
        "elapsed_ms": record["total_ms"],
        "selected_strategy": record["strategy"],
        "policy": record.get("policy"),
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--warmups", type=int, default=2)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.mkdir(parents=True, exist_ok=False)
    settings = load_settings()
    settings.native_slots = 1
    entry = select_model(settings, MODEL)
    if file_hash(Path(entry.path)) != entry.sha256:
        raise ValueError("Model checksum mismatch")
    direct_backend = create_backend(settings.model_copy(deep=True), entry)
    adaptive_backend = create_backend(settings.model_copy(deep=True), entry)
    runtime = Runtime(settings.model_copy(deep=True), MODEL, adaptive_backend)
    manifest = {
        "created_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "model_sha256": entry.sha256,
        "backend_sha256": settings.backend_sha256,
        "backend_commit": settings.backend_commit,
        "source_manifest": source_manifest(),
        "runner_sha256": file_hash(Path(__file__)),
        "policy_file": settings.policy_file,
        "policy_sha256": file_hash(Path(settings.policy_file))
        if settings.policy_file
        else None,
        "workload": WORKLOAD,
        "input_protocol": "Raw prompt string, identical to the exact input-hash framing used by measured-policy.json; no chat template is applied.",
        "workload_prompt_hashes": sorted(
            {
                hashlib.sha256(prompt_for(WORKLOAD, i).encode()).hexdigest()
                for i in range(args.trials)
            }
        ),
        "settings": {
            "threads": settings.threads,
            "context_tokens": settings.context_tokens,
            "slots": 1,
            "worker_address_space_mb": settings.worker_address_space_mb,
        },
        "trials": args.trials,
        "warmups_per_arm": args.warmups,
        "order_seed": 26791,
        "arms": {
            "direct_uncached": "Raw native completion, cache_prompt=false.",
            "direct_native_cache": "Same raw native endpoint, cache_prompt=true on every request; strongest fixed upstream-cache baseline.",
            "lattice_adaptive": "Lattice Runtime with the measured exact-prompt adaptive policy. Only exact qualified hashes may select cached execution.",
        },
        "limitations": [
            "All paths use the same llama.cpp server implementation.",
            "Repeated-prefix workload only; no generalization claim.",
            "Worker cold-start and checksum admission excluded; both workers stay resident.",
            "No official task-quality claim; exact greedy token comparison is enforced.",
        ],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    rows = []
    order = random.Random(26791)
    try:
        await direct_backend.start()
        await adaptive_backend.start()
        for arm in ARMS:
            for i in range(args.warmups):
                prompt = prompt_for(WORKLOAD, i)
                if arm == "lattice_adaptive":
                    await lattice_request(runtime, prompt)
                else:
                    await direct_request(
                        direct_backend, prompt, arm == "direct_native_cache"
                    )
        with (output / "requests.jsonl").open("x") as raw:
            for trial in range(args.trials):
                prompt = prompt_for(WORKLOAD, trial)
                prompt_sha = hashlib.sha256(prompt.encode()).hexdigest()
                arms = ARMS.copy()
                order.shuffle(arms)
                outcomes = {}
                for arm in arms:
                    backend = (
                        adaptive_backend
                        if arm == "lattice_adaptive"
                        else direct_backend
                    )
                    async with RssSampler(backend.process.pid) as memory:
                        result = await (
                            lattice_request(runtime, prompt)
                            if arm == "lattice_adaptive"
                            else direct_request(
                                direct_backend, prompt, arm == "direct_native_cache"
                            )
                        )
                    row = {
                        "trial": trial,
                        "arm": arm,
                        "prompt_sha256": prompt_sha,
                        "model_sha256": entry.sha256,
                        "backend_sha256": settings.backend_sha256,
                        "worker_address_space_mb": settings.worker_address_space_mb,
                        **result,
                        "sampled_worker_rss_peak_bytes": memory.peak_bytes,
                        "sampled_worker_swap_peak_bytes": memory.swap_peak_bytes,
                    }
                    rows.append(row)
                    outcomes[arm] = row
                    raw.write(json.dumps(row, ensure_ascii=False) + "\n")
                    raw.flush()
                token_sets = {arm: row["token_ids"] for arm, row in outcomes.items()}
                pair = {
                    "trial": trial,
                    "prompt_sha256": prompt_sha,
                    "order": arms,
                    "greedy_identical": len({tuple(x) for x in token_sets.values()})
                    == 1,
                    "strategies": {
                        arm: row["selected_strategy"] for arm, row in outcomes.items()
                    },
                    "tokens_cached": {
                        arm: row.get("tokens_cached", 0)
                        for arm, row in outcomes.items()
                    },
                }
                with (output / "pairs.jsonl").open("a") as p:
                    p.write(json.dumps(pair) + "\n")
    finally:
        for backend in (direct_backend, adaptive_backend):
            close = getattr(backend, "aclose", None)
            if close:
                await close()
            else:
                backend.stop()
    summary = {"trials": args.trials, "greedy_mismatches": 0, "arms": {}}
    pair_rows = [
        json.loads(line) for line in (output / "pairs.jsonl").read_text().splitlines()
    ]
    summary["greedy_mismatches"] = sum(not x["greedy_identical"] for x in pair_rows)
    for arm in ARMS:
        selected = [r for r in rows if r["arm"] == arm]
        summary["arms"][arm] = {
            "elapsed_ms": summarize([r["elapsed_ms"] for r in selected]),
            "prompt_tokens": summarize([r["prompt_tokens"] for r in selected]),
            "completion_tokens": summarize([r["completion_tokens"] for r in selected]),
            "tokens_cached": summarize([r["tokens_cached"] for r in selected]),
            "strategies": {
                s: sum(r["selected_strategy"] == s for r in selected)
                for s in sorted({r["selected_strategy"] for r in selected})
            },
            "rss_bytes": summarize(
                [
                    r["sampled_worker_rss_peak_bytes"]
                    for r in selected
                    if r["sampled_worker_rss_peak_bytes"] is not None
                ]
            ),
            "swap_trials": sum(
                (r["sampled_worker_swap_peak_bytes"] or 0) > 0 for r in selected
            ),
        }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(output),
                "trials": args.trials,
                "greedy_mismatches": summary["greedy_mismatches"],
                "strategies": {a: summary["arms"][a]["strategies"] for a in ARMS},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())

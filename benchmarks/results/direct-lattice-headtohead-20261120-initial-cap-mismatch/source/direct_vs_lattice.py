"""Paired single-slot direct llama.cpp versus Lattice runtime CPU benchmark."""

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
from lattice.types import GenerationRequest, Message

ROOT = Path(__file__).resolve().parents[1]
WORKLOADS = [
    "short",
    "long_prompt",
    "long_response",
    "repeated_prefix",
    "memory_constrained",
]
MODEL = "qwen2.5-0.5b-instruct-f16"


async def direct_generate(backend, client, prompt, max_tokens):
    formatted = await backend._post(
        client,
        "/apply-template",
        {"messages": [{"role": "user", "content": prompt}]},
    )
    tokenized = await backend._post(
        client,
        "/tokenize",
        {"content": formatted["prompt"], "add_special": True, "parse_special": True},
    )
    prompt_tokens = tokenized["tokens"]
    if len(prompt_tokens) + max_tokens > backend.settings.context_tokens:
        raise ValueError("Prompt plus output exceeds configured context")
    body = {
        "prompt": prompt_tokens,
        "n_predict": max_tokens,
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
        "cache_prompt": False,
        "return_tokens": True,
    }
    chunks = []
    token_ids = []
    finish_reason = None
    async with client.stream("POST", "/completion", json=body) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            item = json.loads(line[6:])
            if "error" in item:
                raise RuntimeError("Direct backend generation failed")
            if item.get("stop"):
                finish_reason = "length" if item.get("stop_type") == "limit" else "stop"
                break
            tokens = item.get("tokens", [])
            if len(token_ids) + len(tokens) > max_tokens:
                raise RuntimeError("Direct backend violated output cap")
            token_ids.extend(tokens)
            chunks.append(item.get("content", ""))
    if finish_reason is None:
        raise RuntimeError("Direct backend stream lacked terminal stop event")
    return {
        "text": "".join(chunks),
        "token_ids": token_ids,
        "prompt_tokens": len(prompt_tokens),
        "completion_tokens": len(token_ids),
        "finish_reason": finish_reason,
    }


async def run_arm(arm, backend, runtime, request, prompt, cap):
    started = time.perf_counter()
    if arm == "lattice":
        result = await runtime.generate(
            GenerationRequest(
                model=MODEL,
                messages=[Message(role="user", content=prompt)],
                max_tokens=cap,
                temperature=0.0,
                seed=84721,
                timeout_seconds=300.0,
            )
        )
        record = result["metadata"]
        return {
            "text": result["text"],
            "token_ids": result["token_ids"],
            "prompt_tokens": record["prompt_tokens"],
            "completion_tokens": record["completion_tokens"],
            "finish_reason": record["finish_reason"],
            "elapsed_ms": (time.perf_counter() - started) * 1000,
            "queue_wait_ms": record["queue_wait_ms"],
            "selected_strategy": record["strategy"],
        }
    async with httpx.AsyncClient(
        base_url=backend.base_url,
        headers=backend.headers,
        timeout=None,
        trust_env=False,
    ) as client:
        result = await direct_generate(backend, client, prompt, cap)
    result["elapsed_ms"] = (time.perf_counter() - started) * 1000
    result["queue_wait_ms"] = None
    result["selected_strategy"] = "direct_llama_cpp"
    return result


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--warmups", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.trials <= 1000 or not 0 <= args.warmups <= 20:
        raise ValueError("Trials must be 1..1000 and warmups 0..20")
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.mkdir(parents=True, exist_ok=False)
    settings = load_settings()
    settings.native_slots = 1
    model = select_model(settings, MODEL)
    if file_hash(Path(model.path)) != model.sha256:
        raise ValueError("Model checksum mismatch")
    workload_path = ROOT / "benchmarks/workloads/cpu-v2-followup.json"
    spec = json.loads(workload_path.read_text())
    workload_by_id = {item["id"]: item for item in spec["workloads"]}
    workloads = [workload_by_id[name] for name in WORKLOADS]
    lattice_backend = create_backend(settings, model)
    direct_backend = create_backend(settings.model_copy(deep=True), model)
    runtime = Runtime(settings, MODEL, lattice_backend)
    manifest = {
        "created_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "model": model.model_dump(exclude={"path"}),
        "backend_sha256": settings.backend_sha256,
        "backend_commit": settings.backend_commit,
        "workload_file_sha256": file_hash(workload_path),
        "workloads": workloads,
        "trials": args.trials,
        "warmups": args.warmups,
        "sampling": {
            "temperature": 0.0,
            "seed": 84721,
            "top_k": 0,
            "top_p": 1.0,
            "min_p": 0.0,
            "repeat_penalty": 1.0,
        },
        "settings": {
            "threads": settings.threads,
            "context_tokens": settings.context_tokens,
            "native_slots": 1,
            "worker_address_space_mb": settings.worker_address_space_mb,
            "host_reserve_mb": settings.host_reserve_mb,
        },
        "arms": {
            "direct_llama_cpp": "Pinned native server, raw completion endpoint, same chat-template and tokenizer preflight, exact same token-ID completion request used by Lattice.",
            "lattice": "Existing Runtime API; standard mode, including queue, provenance/artifact admission and request metrics.",
        },
        "runner_sha256": file_hash(Path(__file__)),
        "runtime_source_manifest": source_manifest(),
        "platform": __import__("platform").platform(),
        "loadavg_at_start": Path("/proc/loadavg").read_text().split()[:3],
        "timing": "End-to-end wrapper timing including chat template and tokenization for both arms. Server startup, checksum admission, and warmups are excluded.",
        "interpretation": "The direct arm uses the same pinned llama.cpp server as the Lattice arm. This isolates runtime/control-plane overhead and does not compare against another inference engine.",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    rows = []
    pairs = []
    order = random.Random(73411)
    try:
        await lattice_backend.start()
        await direct_backend.start()
        for workload in workloads:
            for index in range(args.warmups):
                prompt = prompt_for(workload, index)
                cap = workload["output_tokens"]
                for arm in ["direct_llama_cpp", "lattice"]:
                    await run_arm(
                        arm,
                        direct_backend
                        if arm == "direct_llama_cpp"
                        else lattice_backend,
                        runtime,
                        None,
                        prompt,
                        cap,
                    )
        with (
            (output / "requests.jsonl").open("x") as raw,
            (output / "pairs.jsonl").open("x") as pair_file,
        ):
            for workload in workloads:
                for trial in range(args.trials):
                    prompt = prompt_for(workload, trial)
                    prompt_sha256 = hashlib.sha256(prompt.encode()).hexdigest()
                    arms = ["direct_llama_cpp", "lattice"]
                    order.shuffle(arms)
                    pair = {
                        "workload": workload["id"],
                        "trial": trial,
                        "prompt_sha256": prompt_sha256,
                        "arms": {},
                    }
                    for arm in arms:
                        backend = (
                            direct_backend
                            if arm == "direct_llama_cpp"
                            else lattice_backend
                        )
                        async with RssSampler(backend.process.pid) as memory:
                            result = await run_arm(
                                arm,
                                backend,
                                runtime,
                                None,
                                prompt,
                                workload["output_tokens"],
                            )
                        row = {
                            "workload": workload["id"],
                            "trial": trial,
                            "arm": arm,
                            "prompt_sha256": prompt_sha256,
                            "model_sha256": model.sha256,
                            "backend_sha256": settings.backend_sha256,
                            "prompt_tokens": result["prompt_tokens"],
                            "completion_tokens": result["completion_tokens"],
                            "finish_reason": result["finish_reason"],
                            "elapsed_ms": result["elapsed_ms"],
                            "queue_wait_ms": result["queue_wait_ms"],
                            "selected_strategy": result["selected_strategy"],
                            "sampled_worker_rss_peak_bytes": memory.peak_bytes,
                            "sampled_worker_swap_peak_bytes": memory.swap_peak_bytes,
                            "text": result["text"],
                            "token_ids": result["token_ids"],
                        }
                        rows.append(row)
                        pair["arms"][arm] = {
                            k: row[k]
                            for k in [
                                "elapsed_ms",
                                "prompt_tokens",
                                "completion_tokens",
                                "finish_reason",
                                "sampled_worker_rss_peak_bytes",
                            ]
                        }
                        raw.write(json.dumps(row, ensure_ascii=False) + "\n")
                        raw.flush()
                    pair["greedy_identical"] = (
                        pair["arms"]["direct_llama_cpp"]["completion_tokens"]
                        == pair["arms"]["lattice"]["completion_tokens"]
                    )
                    direct_tokens = next(
                        r["token_ids"]
                        for r in rows[-2:]
                        if r["arm"] == "direct_llama_cpp"
                    )
                    lattice_tokens = next(
                        r["token_ids"] for r in rows[-2:] if r["arm"] == "lattice"
                    )
                    pair["greedy_identical"] = direct_tokens == lattice_tokens
                    pair["completion_text_identical"] = next(
                        r["text"] for r in rows[-2:] if r["arm"] == "direct_llama_cpp"
                    ) == next(r["text"] for r in rows[-2:] if r["arm"] == "lattice")
                    pairs.append(pair)
                    pair_file.write(json.dumps(pair) + "\n")
                    pair_file.flush()
    finally:
        for backend in [lattice_backend, direct_backend]:
            close = getattr(backend, "aclose", None)
            if close:
                await close()
            else:
                backend.stop()
    summary = {
        "workloads": {},
        "pairs": len(pairs),
        "greedy_mismatches": sum(not r["greedy_identical"] for r in pairs),
        "text_mismatches": sum(not r["completion_text_identical"] for r in pairs),
        "arms": {},
    }
    for arm in ["direct_llama_cpp", "lattice"]:
        summary["arms"][arm] = {}
        for workload in workloads:
            selected = [
                row
                for row in rows
                if row["arm"] == arm and row["workload"] == workload["id"]
            ]
            summary["arms"][arm][workload["id"]] = {
                "completed": len(selected),
                "elapsed_ms": summarize([r["elapsed_ms"] for r in selected]),
                "prompt_tokens": summarize([r["prompt_tokens"] for r in selected]),
                "completion_tokens": summarize(
                    [r["completion_tokens"] for r in selected]
                ),
                "sampled_worker_rss_bytes": summarize(
                    [
                        r["sampled_worker_rss_peak_bytes"]
                        for r in selected
                        if r["sampled_worker_rss_peak_bytes"] is not None
                    ]
                ),
                "swap_observed": sum(
                    (r["sampled_worker_swap_peak_bytes"] or 0) > 0 for r in selected
                ),
            }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(output),
                "pairs": len(pairs),
                "greedy_mismatches": summary["greedy_mismatches"],
                "text_mismatches": summary["text_mismatches"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())

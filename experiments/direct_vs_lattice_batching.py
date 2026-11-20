"""Matched two-slot direct llama.cpp versus Lattice-runtime arrival-trace test."""

import argparse
import asyncio
import datetime
import hashlib
import json
import random
import time
from contextlib import aclosing
from pathlib import Path

import httpx

from lattice.backends import create_backend
from lattice.config import file_hash, load_settings, select_model
from lattice.evaluation.benchmark import prompt_for, source_manifest
from lattice.observability.hardware import cpu_fingerprint
from lattice.observability.measure import RssSampler, summarize
from lattice.runtime import Runtime
from lattice.types import GenerationRequest, Message

ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen2.5-0.5b-instruct-f16"


async def tokenize(backend, client, prompt):
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
    return tokenized["tokens"]


async def direct_stream(backend, prompt, cap, first_token=None):
    chunks = []
    ids = []
    prompt_count = None
    finish_reason = None
    start = time.perf_counter()
    first_text_ms = None
    async with httpx.AsyncClient(
        base_url=backend.base_url,
        headers=backend.headers,
        timeout=None,
        trust_env=False,
    ) as client:
        tokens = await tokenize(backend, client, prompt)
        prompt_count = len(tokens)
        if prompt_count + cap > backend.settings.context_tokens:
            raise ValueError("Prompt plus output exceeds per-request context")
        body = {
            "prompt": tokens,
            "n_predict": cap,
            "stream": True,
            "temperature": 0.0,
            "seed": 0,
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
        async with client.stream("POST", "/completion", json=body) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                if "error" in event:
                    raise RuntimeError("Native direct generation error")
                if event.get("stop"):
                    finish_reason = (
                        "length" if event.get("stop_type") == "limit" else "stop"
                    )
                    break
                next_tokens = event.get("tokens", [])
                if len(ids) + len(next_tokens) > cap:
                    raise RuntimeError("Direct native output exceeded cap")
                ids.extend(next_tokens)
                chunks.append(event.get("content", ""))
                if event.get("content"):
                    if first_text_ms is None:
                        first_text_ms = (time.perf_counter() - start) * 1000
                    if first_token is not None:
                        first_token.set()
    if finish_reason is None:
        raise RuntimeError("Direct native stream ended without terminal event")
    return {
        "text": "".join(chunks),
        "token_ids": ids,
        "prompt_tokens": prompt_count,
        "completion_tokens": len(ids),
        "finish_reason": finish_reason,
        "client_ttft_ms": first_text_ms,
        "total_ms": (time.perf_counter() - start) * 1000,
    }


async def lattice_stream(runtime, prompt, cap, first_token=None):
    request = GenerationRequest(
        model=runtime.model_id,
        messages=[Message(role="user", content=prompt)],
        max_tokens=cap,
        temperature=0.0,
        seed=0,
        timeout_seconds=120.0,
    )
    chunks = []
    ids = []
    metadata = None
    start = time.perf_counter()
    async with aclosing(runtime.events(request)) as stream:
        async for event in stream:
            if event["type"] == "token":
                chunks.append(event["text"])
                ids.extend(event["token_ids"])
                if event["text"] and first_token is not None:
                    first_token.set()
            elif event["type"] == "done":
                metadata = event["record"]
    if metadata is None:
        raise RuntimeError("Lattice runtime ended without completion record")
    return {
        "text": "".join(chunks),
        "token_ids": ids,
        "prompt_tokens": metadata["prompt_tokens"],
        "completion_tokens": metadata["completion_tokens"],
        "finish_reason": metadata["finish_reason"],
        "total_ms": (time.perf_counter() - start) * 1000,
        "queue_wait_ms": metadata["queue_wait_ms"],
        "client_ttft_ms": metadata["client_ttft_ms"],
        "strategy": metadata["strategy"],
    }


async def pair_trial(arm, backend, runtime, index):
    began = time.perf_counter()
    first = asyncio.Event()
    long_prompt = prompt_for(
        {"id": "long_response", "input_words": 24, "output_tokens": 128}, index
    )
    short_prompt = prompt_for(
        {"id": "short", "input_words": 8, "output_tokens": 8}, index
    )
    generator = direct_stream if arm == "direct_llama_cpp" else lattice_stream

    async def long_request():
        return await generator(
            backend if arm == "direct_llama_cpp" else runtime, long_prompt, 128, first
        )

    long_task = asyncio.create_task(long_request())
    try:
        await asyncio.wait_for(first.wait(), 30)
        await asyncio.sleep(0.020)
        if arm == "direct_llama_cpp":
            short_result = await direct_stream(backend, short_prompt, 8)
        else:
            short_result = await lattice_stream(runtime, short_prompt, 8)
        finished_before_long = not long_task.done()
        long_result = await long_task
        return {
            "arm": arm,
            "trial": index,
            "long": long_result,
            "short": short_result,
            "short_finished_before_long": finished_before_long,
            "makespan_ms": (time.perf_counter() - began) * 1000,
        }
    finally:
        if not long_task.done():
            long_task.cancel()
        await asyncio.gather(long_task, return_exceptions=True)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--seed", type=int, default=90413)
    args = parser.parse_args()
    if not 1 <= args.trials <= 1000 or not 0 <= args.warmups <= 20:
        raise ValueError("Trials must be 1..1000 and warmups 0..20")
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.mkdir(parents=True, exist_ok=False)
    settings = load_settings()
    settings.native_slots = 2
    model = select_model(settings, MODEL)
    if file_hash(Path(model.path)) != model.sha256:
        raise ValueError("Model checksum mismatch")
    direct_backend = create_backend(settings.model_copy(deep=True), model)
    lattice_backend = create_backend(settings.model_copy(deep=True), model)
    lattice_runtime = Runtime(settings.model_copy(deep=True), MODEL, lattice_backend)
    manifest = {
        "created_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "model": model.model_dump(exclude={"path"}),
        "backend_commit": settings.backend_commit,
        "backend_sha256": settings.backend_sha256,
        "source_manifest": source_manifest(),
        "runner_sha256": file_hash(Path(__file__)),
        "cpu_fingerprint": cpu_fingerprint(),
        "context_per_slot": settings.context_tokens,
        "native_total_context": settings.context_tokens * 2,
        "threads": settings.threads,
        "worker_address_space_mb": settings.worker_address_space_mb,
        "host_reserve_mb": settings.host_reserve_mb,
        "arrival": "Start long 128-token request; wait for first nonempty generated chunk; wait 20ms; start short 8-token request.",
        "trials": args.trials,
        "warmups_per_arm": args.warmups,
        "arm_order_seed": args.seed,
        "arms": {
            "direct_llama_cpp": "Same pinned two-slot llama.cpp worker/settings; raw concurrent completion streams, native batching enabled.",
            "lattice_runtime": "Same pinned two-slot llama.cpp worker/settings; Lattice Runtime admission, validation, stream handling, cancellation/metrics hooks.",
        },
        "memory_caps": "Both workers use the exact same configured RLIMIT_AS, context, reserve and model artifact.",
        "scope": "One mixed-arrival pattern on one CPU/model. Both workers remain resident, but only one arm is measured at a time.",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    raw_rows = []
    pair_rows = []
    order = random.Random(args.seed)
    try:
        await direct_backend.start()
        await lattice_backend.start()
        for index in range(args.warmups):
            await pair_trial("direct_llama_cpp", direct_backend, lattice_runtime, index)
            await pair_trial("lattice_runtime", lattice_backend, lattice_runtime, index)
        with (
            (output / "requests.jsonl").open("x") as raw,
            (output / "pairs.jsonl").open("x") as pair_file,
        ):
            for index in range(args.trials):
                arms = ["direct_llama_cpp", "lattice_runtime"]
                order.shuffle(arms)
                pair = {"trial": index, "arm_order": arms, "arms": {}}
                for arm in arms:
                    backend = (
                        direct_backend if arm == "direct_llama_cpp" else lattice_backend
                    )
                    runtime = None if arm == "direct_llama_cpp" else lattice_runtime
                    async with RssSampler(backend.process.pid) as memory:
                        result = await pair_trial(arm, backend, runtime, index)
                    row = {
                        "trial": index,
                        "arm": arm,
                        "prompt_pair_sha256": hashlib.sha256(
                            (
                                prompt_for(
                                    {
                                        "id": "long_response",
                                        "input_words": 24,
                                        "output_tokens": 128,
                                    },
                                    index,
                                )
                                + "\0"
                                + prompt_for(
                                    {
                                        "id": "short",
                                        "input_words": 8,
                                        "output_tokens": 8,
                                    },
                                    index,
                                )
                            ).encode()
                        ).hexdigest(),
                        "worker_address_space_mb": settings.worker_address_space_mb,
                        "long": result["long"],
                        "short": result["short"],
                        "short_finished_before_long": result[
                            "short_finished_before_long"
                        ],
                        "makespan_ms": result["makespan_ms"],
                        "sampled_worker_rss_peak_bytes": memory.peak_bytes,
                        "sampled_worker_swap_peak_bytes": memory.swap_peak_bytes,
                    }
                    raw_rows.append(row)
                    pair["arms"][arm] = {
                        "long_token_ids": result["long"]["token_ids"],
                        "short_token_ids": result["short"]["token_ids"],
                        "makespan_ms": result["makespan_ms"],
                        "long_ms": result["long"]["total_ms"],
                        "short_ms": result["short"]["total_ms"],
                        "short_queue_wait_ms": result["short"].get("queue_wait_ms"),
                        "short_finished_before_long": result[
                            "short_finished_before_long"
                        ],
                        "rss_bytes": memory.peak_bytes,
                    }
                    raw.write(json.dumps(row, ensure_ascii=False) + "\n")
                    raw.flush()
                direct, lattice = (
                    pair["arms"]["direct_llama_cpp"],
                    pair["arms"]["lattice_runtime"],
                )
                pair["greedy_identical"] = (
                    direct["long_token_ids"] == lattice["long_token_ids"]
                    and direct["short_token_ids"] == lattice["short_token_ids"]
                )
                pair_rows.append(pair)
                pair_file.write(json.dumps(pair) + "\n")
                pair_file.flush()
    finally:
        for backend in (direct_backend, lattice_backend):
            close = getattr(backend, "aclose", None)
            if close:
                await close()
            else:
                backend.stop()
    arms = {}
    for arm in ("direct_llama_cpp", "lattice_runtime"):
        selected = [row for row in raw_rows if row["arm"] == arm]
        arms[arm] = {
            "long_p50_ms": summarize([row["long"]["total_ms"] for row in selected]),
            "short_p50_ms": summarize([row["short"]["total_ms"] for row in selected]),
            "short_ttft_ms": summarize(
                [
                    row["short"]["client_ttft_ms"]
                    if arm == "lattice_runtime"
                    else row["short"]["total_ms"]
                    for row in selected
                ]
            ),
            "short_queue_ms": summarize(
                [
                    row["short"]["queue_wait_ms"] if arm == "lattice_runtime" else 0.0
                    for row in selected
                ]
            ),
            "makespan_ms": summarize([row["makespan_ms"] for row in selected]),
            "short_finished_before_long": sum(
                row["short_finished_before_long"] for row in selected
            ),
            "rss_bytes": summarize(
                [
                    row["sampled_worker_rss_peak_bytes"]
                    for row in selected
                    if row["sampled_worker_rss_peak_bytes"] is not None
                ]
            ),
            "swap_trials": sum(
                (row["sampled_worker_swap_peak_bytes"] or 0) > 0 for row in selected
            ),
        }
    summary = {
        "trials": len(pair_rows),
        "greedy_mismatches": sum(not pair["greedy_identical"] for pair in pair_rows),
        "arms": arms,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(output),
                "trials": summary["trials"],
                "greedy_mismatches": summary["greedy_mismatches"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())

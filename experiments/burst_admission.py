"""Exogenous burst traces against native slot sweep and admission ablations."""

import argparse
import asyncio
import hashlib
import json
import os
import random
import time
from pathlib import Path

import httpx

from lattice.backends import create_backend
from lattice.backends.http_client import native_ssl_context
from lattice.backends.llama_cpp import LlamaCppBackend
from lattice.config import file_hash, load_settings, select_model
from lattice.evaluation.benchmark import source_manifest
from lattice.observability.measure import RssSampler, summarize
from lattice.runtime import Runtime
from lattice.scheduler.fair import FairSemaphore
from lattice.types import GenerationRequest, Optimization

ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen2.5-0.5b-instruct-f16"
ARMS = [
    "native1",
    "native2",
    "native3",
    "native4",
    "native8",
    "lattice_fifo2",
    "lattice_cost2",
    "simple_cost2",
    "lattice_cost4",
    "simple_cost4",
    "lattice_cost3",
    "simple_cost3",
    "lattice_reserve4",
    "lattice_coalesce8",
    "lattice_coalesce4",
    "native8_b64",
    "native8_b128",
    "native8_b512",
    "native8_b1024",
    "lattice_coalesce4_b64",
    "lattice_coalesce4_b128",
    "lattice_coalesce4_b512",
    "lattice_coalesce4_b1024",
]
WORDS = [
    "amber",
    "birch",
    "cedar",
    "delta",
    "elm",
    "fern",
    "gold",
    "hazel",
    "iris",
    "jade",
    "kelp",
    "lilac",
    "maple",
    "navy",
    "olive",
    "pearl",
    "quartz",
    "reed",
    "sage",
    "teal",
    "umber",
    "violet",
    "willow",
    "xenon",
    "yarrow",
    "zinc",
]


class NativeSlotOnlyCache(LlamaCppBackend):
    """Upstream per-slot caching without the optional RAM snapshot archive."""

    def extra_server_arguments(self):
        return ["--cache-ram", "0", "--no-cache-idle-slots", "--cache-reuse", "0"]


def make_trace(seed, bulk=6, interactive=6):
    rng = random.Random(seed)
    rows = []
    for i in range(bulk + interactive):
        is_short = i >= bulk
        identifier = f"{seed}-{i}"
        content = " ".join(rng.choices(WORDS, k=900 if not is_short else 8))
        gold = rng.choice(WORDS)
        prompt = f"Data {identifier}: {content}\nFinal value: {gold}\nCopy only the final value:"
        rows.append(
            {
                "id": identifier,
                "class": "interactive" if is_short else "bulk",
                "arrival_seconds": (0.030 + (i - bulk) * 0.002)
                if is_short
                else i * 0.002,
                "prompt": prompt,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "gold": gold,
                "max_tokens": 8 if is_short else 16,
            }
        )
    return rows


async def direct(backend, request):
    async with httpx.AsyncClient(
        base_url=backend.base_url,
        headers=backend.headers,
        timeout=None,
        trust_env=False,
        verify=native_ssl_context(),
    ) as client:
        response = await client.post(
            "/tokenize",
            json={
                "content": request["prompt"],
                "add_special": True,
                "parse_special": True,
            },
        )
        response.raise_for_status()
        tokens = response.json()["tokens"]
        if len(tokens) + request["max_tokens"] > backend.settings.context_tokens:
            raise ValueError("Context overflow; no truncation")
        body = {
            "prompt": tokens,
            "n_predict": request["max_tokens"],
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
            "cache_prompt": True,
            "return_tokens": True,
        }
        ids = []
        chunks = []
        terminal = None
        first = None
        started = time.perf_counter()
        async with client.stream("POST", "/completion", json=body) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                if "error" in event:
                    raise RuntimeError("Native generation error")
                if event.get("stop"):
                    terminal = event
                    break
                if event.get("content") and first is None:
                    first = (time.perf_counter() - started) * 1000
                ids.extend(event.get("tokens", []))
                chunks.append(event.get("content", ""))
        if (
            terminal is None
            or terminal.get("truncated")
            or len(ids) > request["max_tokens"]
        ):
            raise ValueError("Native completion contract failed")
        return {
            "token_ids": ids,
            "text": "".join(chunks),
            "prompt_tokens": len(tokens),
            "completion_tokens": len(ids),
            "finish_reason": terminal.get("stop_type"),
            "backend_timings": terminal.get("timings"),
            "native_first_text_ms": first,
        }


async def run_trace(arm, trace, output):
    full_arm = arm
    native_no_ram = arm.endswith("_noram")
    if native_no_ram:
        arm = arm.removesuffix("_noram")
        if not arm.startswith("native"):
            raise ValueError("Native RAM-cache ablation requires a native arm")
    isolated = arm.endswith("_isolated")
    if isolated:
        arm = arm.removesuffix("_isolated")
        if not arm.startswith("lattice_"):
            raise ValueError("Isolated control requires a Lattice arm")
    cached = arm.endswith("_cached")
    if cached:
        arm = arm.removesuffix("_cached")
        if not arm.startswith("lattice_"):
            raise ValueError(
                "Cached suffix selects the explicit Lattice slot-cache path"
            )
    if "_b" in arm:
        arm, batch = arm.rsplit("_b", 1)
    else:
        batch = "256"
    settings = load_settings()
    if cached or isolated:
        settings.concurrent_prefix_cache = True
        settings.cache_limit_mb = 64
        settings.cache_min_tokens = 1
    settings.batch_tokens = int(batch)
    settings.ubatch_tokens = min(256, int(batch))
    settings.policy_file = None
    settings.max_queue = 128
    settings.log_directory = str(output / "private" / arm)
    entry = select_model(settings, MODEL)
    if arm.startswith("native"):
        slots = int(arm[6:])
        backend = (NativeSlotOnlyCache if native_no_ram else LlamaCppBackend)(
            settings, entry
        )
        backend.native_slots = slots
        runtime = None
    elif arm.startswith("simple_cost"):
        slots = int(arm[-1])
        backend = LlamaCppBackend(settings, entry)
        backend.native_slots = slots
        runtime = None
    else:
        slots = int(arm[-1])
        settings.native_slots = slots
        settings.admission_policy = (
            "priority_cost_coalesce"
            if arm.startswith("lattice_coalesce")
            else "priority_cost_reserve"
            if arm.startswith("lattice_reserve")
            else "priority_cost"
            if arm.startswith("lattice_cost")
            else "priority_fifo"
        )
        backend = create_backend(settings, entry)
        runtime = Runtime(settings, MODEL, backend)
    semaphore = (
        FairSemaphore(slots, cost_aware=True) if arm.startswith("simple_cost") else None
    )
    results = []
    try:
        await backend.start()
        worker_cpu_cgroup = (
            Path(f"/proc/{backend.process.pid}/cgroup").read_text().strip()
        )
        # Identical one-request warmup; prompt does not appear in any measured trace.
        warmup = {"prompt": "Return only READY:", "max_tokens": 8}
        if runtime:
            await runtime.generate(
                GenerationRequest(
                    model=MODEL,
                    prompt=warmup["prompt"],
                    max_tokens=8,
                    timeout_seconds=120.0,
                    optimization=Optimization(mode="cached" if cached else "standard"),
                )
            )
        else:
            await direct(backend, warmup)
        origin = time.perf_counter()

        async def submit(request):
            await asyncio.sleep(
                max(0, origin + request["arrival_seconds"] - time.perf_counter())
            )
            dispatch = time.perf_counter()
            acquired = False
            try:
                if semaphore:
                    await semaphore.acquire(
                        0, len(request["prompt"].encode()) + 64 * request["max_tokens"]
                    )
                    acquired = True
                if runtime:
                    result = await runtime.generate(
                        GenerationRequest(
                            model=MODEL,
                            prompt=request["prompt"],
                            max_tokens=request["max_tokens"],
                            timeout_seconds=120.0,
                            optimization=Optimization(
                                mode="cached" if cached else "standard"
                            ),
                        )
                    )
                    data = {
                        "token_ids": result["token_ids"],
                        "text": result["text"],
                        "prompt_tokens": result["metadata"]["prompt_tokens"],
                        "completion_tokens": result["metadata"]["completion_tokens"],
                        "finish_reason": result["metadata"]["finish_reason"],
                        "queue_wait_ms": result["metadata"]["queue_wait_ms"],
                        "backend_timings": result["metadata"]["backend_timings"],
                        "strategy": result["metadata"]["strategy"],
                        "tokens_cached": result["metadata"]["tokens_cached"],
                    }
                else:
                    data = await direct(backend, request)
                finish = time.perf_counter()
                row = {k: v for k, v in request.items() if k != "prompt"}
                row.update(
                    data,
                    status="completed",
                    arm=arm,
                    native_slots=slots,
                    dispatch_lateness_ms=(
                        dispatch - origin - request["arrival_seconds"]
                    )
                    * 1000,
                    latency_ms=(finish - origin - request["arrival_seconds"]) * 1000,
                    submitted_to_finish_ms=(finish - dispatch) * 1000,
                    completed_offset_seconds=finish - origin,
                    exact_correct=data["text"].strip() == request["gold"],
                )
            except Exception as exc:  # noqa: BLE001 — retain every failed benchmark request
                row = {
                    "id": request["id"],
                    "class": request["class"],
                    "arm": arm,
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "arrival_seconds": request["arrival_seconds"],
                }
            finally:
                if acquired:
                    semaphore.release()
            results.append(row)

        async with (
            RssSampler(backend.process.pid) as memory,
            RssSampler(os.getpid()) as parent_memory,
        ):
            await asyncio.gather(*(submit(request) for request in trace))
        makespan = time.perf_counter() - origin
        completed = [r for r in results if r["status"] == "completed"]
        return {
            "arm": full_arm,
            "batch_tokens": settings.batch_tokens,
            "ubatch_tokens": settings.ubatch_tokens,
            "native_slots": slots,
            "cache_policy": "explicit_slot_compatible"
            if cached
            else "isolated_no_reuse"
            if isolated
            else "disabled"
            if runtime
            else "native_prefix",
            "cache_limit_mb": settings.cache_limit_mb,
            "cache_min_tokens": settings.cache_min_tokens,
            "native_ram_archive": False
            if native_no_ram or cached or isolated
            else "upstream_default",
            "worker_cpu_cgroup": worker_cpu_cgroup,
            "rows": results,
            "makespan_seconds": makespan,
            "tokens_per_second": sum(r["completion_tokens"] for r in completed)
            / makespan,
            "worker_rss_peak_bytes": memory.peak_bytes,
            "control_plane_rss_peak_bytes": parent_memory.peak_bytes,
            "worker_swap_peak_bytes": memory.swap_peak_bytes,
            "summary": {
                group: summarize(
                    [r["latency_ms"] for r in completed if r["class"] == group]
                )
                for group in ["interactive", "bulk"]
            },
            "failures": len(results) - len(completed),
        }
    finally:
        close = getattr(backend, "aclose", None)
        if close:
            await close()
        else:
            backend.stop()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=1001)
    parser.add_argument("--arms", nargs="+", choices=ARMS, default=ARMS)
    parser.add_argument("--traces", type=int, default=1)
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    settings = load_settings()
    entry = select_model(settings, MODEL)
    manifest = {
        "seed": args.seed,
        "trace_count": args.traces,
        "traces": [make_trace(args.seed + i) for i in range(args.traces)],
        "arms": args.arms,
        "backend_sha256": settings.backend_sha256,
        "model_sha256": entry.sha256,
        "source": source_manifest(),
        "runner_sha256": file_hash(Path(__file__)),
        "worker_address_space_mb": settings.worker_address_space_mb,
        "context_per_request": settings.context_tokens,
        "threads": settings.threads,
        "protocol": "Exogenous burst: six diverse long-input requests followed by six short-input requests, every arm receives identical prompts and arrival offsets; arrivals never wait for any completion. Native caching enabled on direct baselines; no forced output length. Both worker and control-plane RSS sampled. Simple-cost ablation uses identical size-proxy priority queue outside Lattice Runtime. This is a development trace, not held-out confirmation.",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    rng = random.Random(args.seed)
    all_results = []
    with (out / "results.jsonl").open("x") as raw:
        for index, trace in enumerate(manifest["traces"]):
            arms = args.arms.copy()
            rng.shuffle(arms)
            for arm in arms:
                result = await run_trace(arm, trace, out)
                result["trace"] = index
                all_results.append(result)
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
                    flush=True,
                )
    (out / "summary.json").write_text(json.dumps(all_results, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main())

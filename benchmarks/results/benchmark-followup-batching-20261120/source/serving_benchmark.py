"""Paired mixed-length experiment: fixed model/weights, one versus two native slots."""

import argparse
import asyncio
import json
import random
import time
from contextlib import aclosing
from pathlib import Path

from lattice.backends import create_backend
from lattice.config import load_settings
from lattice.evaluation.benchmark import prompt_for, source_manifest
from lattice.evaluation.quality import score
from lattice.observability.hardware import cpu_fingerprint
from lattice.observability.measure import RssSampler, export_csv, summarize
from lattice.runtime import Runtime
from lattice.types import GenerationRequest

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--trials", type=int, default=30)
parser.add_argument("--quality", action="store_true")
a = parser.parse_args()


async def trial(runtime, index):
    start = time.perf_counter()
    first = asyncio.Event()

    async def long_request():
        tokens = []
        record = None
        request = GenerationRequest(
            model=runtime.model_id,
            prompt=prompt_for(
                {"id": "long_response", "input_words": 24, "output_tokens": 128}, index
            ),
            max_tokens=128,
            timeout_seconds=120.0,
        )
        async with aclosing(runtime.events(request)) as stream:
            async for event in stream:
                if event["type"] == "token":
                    tokens.extend(event["token_ids"])
                    if event["text"]:
                        first.set()
                elif event["type"] == "done":
                    record = event["record"]
        return {"token_ids": tokens, "metadata": record}

    long = asyncio.create_task(long_request())
    try:
        await asyncio.wait_for(first.wait(), 30)
        await asyncio.sleep(0.02)
        short = await runtime.generate(
            GenerationRequest(
                model=runtime.model_id,
                prompt=prompt_for(
                    {"id": "short", "input_words": 8, "output_tokens": 8}, index
                ),
                max_tokens=8,
                timeout_seconds=120.0,
            )
        )
        overlapped = not long.done()
        long_result = await long
        return {
            "long": long_result,
            "short": short,
            "short_finished_before_long": overlapped,
            "makespan_ms": (time.perf_counter() - start) * 1000,
        }
    finally:
        if not long.done():
            long.cancel()
        await asyncio.gather(long, return_exceptions=True)


async def main():
    if not 1 <= a.trials <= 1000:
        raise ValueError("Trials must be 1..1000")
    a.output.mkdir(parents=True, exist_ok=False)
    base = load_settings()
    base.policy_file = None
    runtimes = {}
    backends = {}
    for slots in (1, 2):
        settings = base.model_copy(deep=True)
        settings.native_slots = slots
        settings.log_directory = str(a.output / f"private-{slots}")
        backend = create_backend(settings, settings.models[0])
        backends[slots] = backend
        runtimes[slots] = Runtime(settings, settings.models[0].id, backend)
    manifest = {
        "source": source_manifest(),
        "model": base.models[0].model_dump(exclude={"path"}),
        "backend_sha256": base.backend_sha256,
        "backend_commit": base.backend_commit,
        "trials": a.trials,
        "warmups_per_arm": 3,
        "seed": 4071,
        "threads": base.threads,
        "per_request_context": base.context_tokens,
        "native_total_context": {
            "1": base.context_tokens,
            "2": base.context_tokens * 2,
        },
        "worker_address_space_mb": base.worker_address_space_mb,
        "cpu_fingerprint": cpu_fingerprint(),
        "sampling": {"temperature": 0.0, "seed": 0, "long_cap": 128, "short_cap": 8},
        "short_arrival": "20 ms after first nonempty long text chunk",
        "scope": "Both workers resident, only one arm executing at a time. Paired randomized arm order; same public synthetic prompt variants.",
    }
    (a.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    rows = []
    pairs = []
    rng = random.Random(4071)
    quality = None
    try:
        for backend in backends.values():
            await backend.start()
        for slots in (1, 2):
            for warmup in range(3):
                await trial(runtimes[slots], warmup)
        with (
            (a.output / "requests.jsonl").open("x") as raw,
            (a.output / "pairs.jsonl").open("x") as pair_file,
        ):
            for index in range(a.trials):
                arms = [1, 2]
                rng.shuffle(arms)
                results = {}
                for slots in arms:
                    backend = backends[slots]
                    async with RssSampler(backend.process.pid) as memory:
                        result = await trial(runtimes[slots], index)
                    results[slots] = result
                    for role in ["long", "short"]:
                        row = dict(result[role]["metadata"])
                        row.update(
                            arm=f"slots-{slots}",
                            workload=role,
                            trial=index,
                            token_ids=result[role]["token_ids"],
                            sampled_worker_rss_peak_bytes=memory.peak_bytes,
                            sampled_worker_swap_peak_bytes=memory.swap_peak_bytes,
                        )
                        rows.append(row)
                        raw.write(json.dumps(row) + "\n")
                        raw.flush()
                    pair = {
                        "trial": index,
                        "slots": slots,
                        "makespan_ms": result["makespan_ms"],
                        "short_finished_before_long": result[
                            "short_finished_before_long"
                        ],
                    }
                    pairs.append(pair)
                    pair_file.write(json.dumps(pair) + "\n")
                    pair_file.flush()
                for role in ["long", "short"]:
                    if results[1][role]["token_ids"] != results[2][role]["token_ids"]:
                        (a.output / "quality-mismatch.json").write_text(
                            json.dumps(
                                {"trial": index, "role": role, "results": results},
                                indent=2,
                            )
                            + "\n"
                        )
                        raise RuntimeError(
                            "Native batching changed greedy output; experiment stopped"
                        )
        if a.quality:
            tasks = json.loads(
                Path("benchmarks/datasets/quality-smoke.json").read_text()
            )["tasks"]
            outcomes = {}
            for slots in (1, 2):

                async def one(task, slots=slots):
                    result = await runtimes[slots].generate(
                        GenerationRequest(
                            model=runtimes[slots].model_id,
                            messages=[{"role": "user", "content": task["prompt"]}],
                            max_tokens=96,
                            timeout_seconds=120.0,
                        )
                    )
                    return {
                        "id": task["id"],
                        "passed": score(task, result["text"]),
                        "token_ids": result["token_ids"],
                        "text": result["text"],
                    }

                outcomes[slots] = []
                for i in range(0, len(tasks), slots):
                    outcomes[slots].extend(
                        await asyncio.gather(
                            *(one(task) for task in tasks[i : i + slots])
                        )
                    )
            quality = {
                "source_sha256": __import__("hashlib")
                .sha256(Path("benchmarks/datasets/quality-smoke.json").read_bytes())
                .hexdigest(),
                "outcomes": outcomes,
                "greedy_mismatches": [
                    left["id"]
                    for left, right in zip(outcomes[1], outcomes[2], strict=True)
                    if left["token_ids"] != right["token_ids"]
                ],
                "scope": "Public 22-task smoke suite, not representative held-out task noninferiority",
            }
    finally:
        for backend in backends.values():
            close = getattr(backend, "aclose", None)
            if close:
                await close()
            else:
                backend.stop()
    summary = {"quality": quality, "arms": {}}
    for slots in (1, 2):
        arm = f"slots-{slots}"
        selected = [r for r in rows if r["arm"] == arm]
        groups = [p for p in pairs if p["slots"] == slots]
        summary["arms"][arm] = {
            "short_latency_ms": summarize(
                [r["total_ms"] for r in selected if r["workload"] == "short"]
            ),
            "short_ttft_ms": summarize(
                [r["client_ttft_ms"] for r in selected if r["workload"] == "short"]
            ),
            "short_queue_ms": summarize(
                [r["queue_wait_ms"] for r in selected if r["workload"] == "short"]
            ),
            "long_latency_ms": summarize(
                [r["total_ms"] for r in selected if r["workload"] == "long"]
            ),
            "makespan_ms": summarize([p["makespan_ms"] for p in groups]),
            "short_finished_before_long": sum(
                p["short_finished_before_long"] for p in groups
            ),
            "worker_rss_bytes": summarize(
                [r["sampled_worker_rss_peak_bytes"] for r in selected]
            ),
            "worker_swap_observed_trials": sum(
                (r["sampled_worker_swap_peak_bytes"] or 0) > 0 for r in selected
            ),
            "aggregate_generated_tokens_per_second": sum(
                r["completion_tokens"] for r in selected
            )
            / (sum(p["makespan_ms"] for p in groups) / 1000),
        }
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    export_csv(rows, a.output / "requests.csv")
    if quality and quality["greedy_mismatches"]:
        raise RuntimeError(
            "Smoke-suite greedy output changed; quality qualification rejected"
        )


asyncio.run(main())

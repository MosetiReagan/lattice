"""Reproducible, bounded CPU benchmark runner. Every observation is retained."""

import asyncio
import datetime
import hashlib
import importlib.metadata
import json
import os
import platform
import random
import sys
import time
from pathlib import Path

from lattice.backends import create_backend
from lattice.config import Settings, file_hash, select_model
from lattice.observability.measure import RssSampler, export_csv, summarize
from lattice.runtime import Runtime
from lattice.types import GenerationRequest, LatticeError

from .quality import score


def source_manifest() -> dict:
    root = Path(__file__).resolve().parents[3]
    files = {
        str(p.relative_to(root)): file_hash(p)
        for p in sorted((root / "src").rglob("*.py"))
    }
    for name in ["uv.lock", "pyproject.toml"]:
        if (root / name).exists():
            files[name] = file_hash(root / name)
    return {
        "files": files,
        "sha256": hashlib.sha256(
            json.dumps(files, sort_keys=True).encode()
        ).hexdigest(),
    }


def prompt_for(workload: dict, trial: int) -> str:
    # Fixed public synthetic prompt; word lengths are targets, token counts are measured.
    words = [
        "The",
        "careful",
        "engineer",
        "records",
        "each",
        "observation",
        "before",
        "comparing",
        "the",
        "measured",
        "results.",
        "The",
        "model",
        "completes",
        "the",
        "next",
        "sentence",
        "using",
        "the",
        "supplied",
        "context.",
    ]
    count = workload["input_words"]
    if workload["id"] == "mixed":
        count = [24, 128, 512, 900][trial % 4]
    return (
        " ".join((words * (count // len(words) + 1))[:count])
        + f"\nReport {trial % 4}: The next step is"
    )


async def run_benchmark(
    settings: Settings,
    model_id: str,
    workload_file: Path,
    output: Path,
    trials: int | None = None,
    warmups: int | None = None,
    selected: list[str] | None = None,
    quality_file: Path | None = None,
) -> dict:
    spec = json.loads(workload_file.read_text())
    repeat = trials if trials is not None else spec["trials"]
    warmup = warmups if warmups is not None else spec["warmups"]
    if not 1 <= repeat <= 1000 or not 0 <= warmup <= 20:
        raise LatticeError("Trials must be 1..1000 and warmups 0..20")
    workloads = [
        w for w in spec["workloads"] if selected is None or w["id"] in selected
    ]
    if not workloads or (selected and set(selected) - {w["id"] for w in workloads}):
        raise LatticeError("Unknown or empty workload selection")
    entry = select_model(settings, model_id)
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "created_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "model": entry.model_dump(exclude={"path"}),
        "backend_commit": settings.backend_commit,
        "backend_sha256": settings.backend_sha256,
        "shared_libraries": settings.backend_files,
        "settings": settings.model_dump(
            exclude={"models", "backend_binary", "log_directory"}
        ),
        "workload_file_sha256": file_hash(workload_file),
        "workloads": workloads,
        "trials": repeat,
        "warmups": warmup,
        "seed": 1701,
        "source": source_manifest(),
        "python": sys.version,
        "platform": platform.platform(),
        "packages": {
            p: importlib.metadata.version(p) for p in ["httpx", "pydantic", "fastapi"]
        },
        "loadavg_at_start": (
            Path("/proc/loadavg").read_text().split()[:3]
            if Path("/proc/loadavg").exists()
            else [str(x) for x in os.getloadavg()[:3]]
        ),
        "sampling": {
            "temperature": 0.0,
            "seed": 0,
            "stop": "native EOS; output cap is not guaranteed length",
        },
        "rss_interval_seconds": 0.01,
        "energy": None,
        "gpu": None,
        "note": "Single VM session, not three-session acceptance evidence; word targets are not token counts.",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    records, loads = [], []
    ordered = list(workloads)
    random.Random(1701).shuffle(ordered)
    with (output / "requests.jsonl").open("x") as raw:
        for workload in ordered:
            local = settings.model_copy(deep=True)
            local.log_directory = str(output / "private")
            if "worker_limit_mb" in workload:
                local.worker_address_space_mb = workload["worker_limit_mb"]
            backend = create_backend(local, entry)
            runtime = Runtime(local, model_id, backend)
            try:
                started = time.perf_counter()
                try:
                    await backend.start()
                    loads.append(
                        {
                            "workload": workload["id"],
                            "status": "ready",
                            "worker_startup_ms": (time.perf_counter() - started) * 1000,
                        }
                    )
                except LatticeError as exc:
                    loads.append(
                        {
                            "workload": workload["id"],
                            "status": "error",
                            "error_code": exc.code,
                        }
                    )
                    # Keep failed admissions in the report. Do not retry an impossible config N times.
                    for index in range(repeat):
                        item = {
                            "workload": workload["id"],
                            "trial": index,
                            "status": "startup_failed",
                            "error_code": exc.code,
                            "model": model_id,
                            "total_ms": None,
                        }
                        records.append(item)
                        raw.write(json.dumps(item) + "\n")
                    raw.flush()
                    continue

                async def one(
                    index: int,
                    measured: bool = True,
                    workload=workload,
                    backend=backend,
                    runtime=runtime,
                ) -> dict:
                    request = GenerationRequest(
                        model=model_id,
                        prompt=prompt_for(workload, index),
                        max_tokens=workload["output_tokens"],
                        timeout_seconds=300.0,
                    )
                    async with RssSampler(
                        backend.process.pid if backend.process else -1
                    ) as memory:
                        start = time.perf_counter()
                        try:
                            result = await runtime.generate(request)
                            item = dict(result["metadata"])
                            item["output_sha256"] = hashlib.sha256(
                                json.dumps(result["token_ids"]).encode()
                            ).hexdigest()
                            item["text"] = result["text"]
                            item["token_ids"] = result["token_ids"]
                        except LatticeError as exc:
                            item = {
                                "status": "error",
                                "error_code": exc.code,
                                "model": model_id,
                                "total_ms": (time.perf_counter() - start) * 1000,
                            }
                    item.update(
                        workload=workload["id"],
                        trial=index,
                        sampled_worker_rss_peak_bytes=memory.peak_bytes,
                        sampled_worker_swap_peak_bytes=memory.swap_peak_bytes,
                        rss_samples=memory.samples,
                        input_sha256=hashlib.sha256(
                            request.prompt.encode()
                        ).hexdigest(),
                    )
                    if measured:
                        records.append(item)
                        raw.write(json.dumps(item) + "\n")
                        raw.flush()
                    return item

                for index in range(warmup):
                    await one(index, False)
                concurrency = workload.get("concurrency", 1)
                began = time.perf_counter()
                for index in range(0, repeat, concurrency):
                    await asyncio.gather(
                        *(
                            one(i)
                            for i in range(index, min(index + concurrency, repeat))
                        )
                    )
                elapsed = time.perf_counter() - began
                loads[-1]["measurement_makespan_seconds"] = elapsed
            finally:
                close = getattr(backend, "aclose", None)
                if close:
                    await close()
                else:
                    backend.stop()
    summary = {"workloads": {}, "load_observations": loads, "quality": None}
    for workload in workloads:
        rows = [r for r in records if r["workload"] == workload["id"]]
        passed = [r for r in rows if r["status"] == "completed"]
        elapsed = next(
            (
                r.get("measurement_makespan_seconds")
                for r in loads
                if r["workload"] == workload["id"]
            ),
            None,
        )
        summary["workloads"][workload["id"]] = {
            "attempted": len(rows),
            "completed": len(passed),
            "failed": len(rows) - len(passed),
            "latency_ms": summarize([r["total_ms"] for r in passed]),
            "ttft_ms": summarize(
                [r["client_ttft_ms"] for r in passed if r["client_ttft_ms"] is not None]
            ),
            "queue_ms": summarize([r["queue_wait_ms"] for r in passed]),
            "sampled_worker_rss_bytes": summarize(
                [
                    r["sampled_worker_rss_peak_bytes"]
                    for r in passed
                    if r["sampled_worker_rss_peak_bytes"] is not None
                ]
            ),
            "aggregate_generated_tokens_per_second": sum(
                r["completion_tokens"] for r in passed
            )
            / elapsed
            if elapsed
            else None,
            "aggregate_requests_per_second": len(passed) / elapsed if elapsed else None,
            "output_tokens": summarize([r["completion_tokens"] for r in passed]),
            "swap_sampled_trials": sum(
                r.get("sampled_worker_swap_peak_bytes") is not None for r in passed
            ),
            "worker_swap_observed_trials": sum(
                (r.get("sampled_worker_swap_peak_bytes") or 0) > 0 for r in passed
            ),
        }
    if quality_file is not None:
        backend = create_backend(settings, entry)
        runtime = Runtime(settings, model_id, backend)
        tasks = json.loads(quality_file.read_text())["tasks"]
        outcomes = []
        try:
            await backend.start()
            for task in tasks:
                result = await runtime.generate(
                    GenerationRequest(
                        model=model_id,
                        messages=[{"role": "user", "content": task["prompt"]}],
                        max_tokens=96,
                        timeout_seconds=120.0,
                    )
                )
                outcomes.append(
                    {
                        "id": task["id"],
                        "category": task["category"],
                        "text": result["text"],
                        "passed": score(task, result["text"]),
                        "token_ids": result["token_ids"],
                    }
                )
        finally:
            close = getattr(backend, "aclose", None)
            if close:
                await close()
            else:
                backend.stop()
        summary["quality"] = {
            "dataset_sha256": file_hash(quality_file),
            "tasks": len(outcomes),
            "passed": sum(t["passed"] for t in outcomes),
            "outcomes": outcomes,
            "scope": "Public self-authored smoke suite; no representative/held-out claim",
        }
    export_csv(records, output / "requests.csv")
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary

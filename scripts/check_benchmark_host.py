"""Measure CPU availability before spending a frozen model benchmark budget."""

import argparse
import datetime
import json
import multiprocessing
import os
import queue
import time
from pathlib import Path

from lattice.config import file_hash
from lattice.observability.host import (
    CpuStealSampler,
    cpu_bandwidth_snapshot,
    cpu_preflight_eligible,
)


def worker(barrier, output, duration):
    barrier.wait(timeout=30)
    start, cpu_start = time.perf_counter(), time.process_time()
    value = 1
    while time.perf_counter() - start < duration:
        for _ in range(1000):
            value = (value * 17 + 11) % 10000019
    output.put(
        {
            "cpu_seconds": time.process_time() - cpu_start,
            "wall_seconds": time.perf_counter() - start,
        }
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=3.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--interval-steal-max", type=float, default=0.10)
    args = parser.parse_args()
    if (
        not 1 <= args.workers <= (os.cpu_count() or 1)
        or not 1 <= args.duration <= 120
        or not 0 < args.interval_steal_max <= 0.10
    ):
        raise ValueError(
            "Bounded CPU probe requires available workers, 1-120 seconds and an interval steal limit in (0, 0.10]"
        )
    mp = multiprocessing.get_context("spawn")
    barrier, output = mp.Barrier(args.workers + 1), mp.Queue()
    processes = [
        mp.Process(target=worker, args=(barrier, output, args.duration))
        for _ in range(args.workers)
    ]
    results = []
    host_cpu = CpuStealSampler()
    try:
        for process in processes:
            process.start()
        host_cpu.sample()
        barrier.wait(timeout=30)
        next_sample = time.perf_counter() + host_cpu.interval
        while len(results) < args.workers:
            timeout = max(0.01, min(0.25, next_sample - time.perf_counter()))
            try:
                results.append(output.get(timeout=timeout))
            except queue.Empty:
                pass
            now = time.perf_counter()
            if now >= next_sample:
                host_cpu.sample()
                next_sample = now + host_cpu.interval
        host_cpu.sample()
        for process in processes:
            process.join(timeout=5)
            if process.exitcode != 0:
                raise RuntimeError("CPU probe worker failed")
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        output.close()
    steal = host_cpu.summary()
    available = sum(item["cpu_seconds"] for item in results) / sum(
        item["wall_seconds"] for item in results
    )
    report = {
        "utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "workers": args.workers,
        "cpu_bandwidth": cpu_bandwidth_snapshot(),
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "duration_seconds": args.duration,
        "worker_samples": results,
        "available_cpu_fraction": available,
        "cpu_steal_fraction": steal.get("aggregate_steal_fraction"),
        "cpu_steal": steal,
        "checker_sha256": file_hash(Path(__file__)),
        "eligibility_limits": {
            "aggregate_steal_max": 0.05,
            "interval_steal_max": args.interval_steal_max,
            "available_cpu_min": 0.90,
        },
        "eligible": cpu_preflight_eligible(
            steal, available, interval_steal_max=args.interval_steal_max
        ),
        "contract": (
            "Preflight only, not an inference speed result. Require <=5% aggregate steal, "
            f"<={args.interval_steal_max:.1%} per sampled interval, and >=90% requested CPU time. "
            "This does not guarantee future availability; confirmation must independently "
            "record and gate every arm's steal counters."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

"""Measure CPU availability before spending a frozen model benchmark budget."""

import argparse
import datetime
import json
import multiprocessing
import os
import time
from pathlib import Path

from lattice.observability.host import read_cpu_times, steal_fraction


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
    args = parser.parse_args()
    if not 1 <= args.workers <= (os.cpu_count() or 1) or not 1 <= args.duration <= 30:
        raise ValueError(
            "Bounded CPU probe requires available workers and 1-30 seconds"
        )
    mp = multiprocessing.get_context("spawn")
    barrier, output = mp.Barrier(args.workers + 1), mp.Queue()
    processes = [
        mp.Process(target=worker, args=(barrier, output, args.duration))
        for _ in range(args.workers)
    ]
    results = []
    try:
        for process in processes:
            process.start()
        before = read_cpu_times()
        barrier.wait(timeout=30)
        results = [output.get(timeout=args.duration + 30) for _ in processes]
        after = read_cpu_times()
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
    fraction = steal_fraction(before, after)
    available = sum(item["cpu_seconds"] for item in results) / sum(
        item["wall_seconds"] for item in results
    )
    report = {
        "utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "workers": args.workers,
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "duration_seconds": args.duration,
        "worker_samples": results,
        "available_cpu_fraction": available,
        "cpu_steal_fraction": fraction,
        "eligible": fraction is not None and fraction <= 0.05 and available >= 0.9,
        "contract": "Preflight only, not an inference speed result. Require <=5% aggregate CPU steal and >=90% requested CPU time. This does not guarantee future availability; confirmation must independently record and gate every arm's steal counters.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

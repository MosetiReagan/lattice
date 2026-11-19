"""Linux worker RSS sampling, raw record exports and descriptive statistics."""

import asyncio
import csv
import math
import statistics
from pathlib import Path


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    at = (len(ordered) - 1) * q
    lo, hi = math.floor(at), math.ceil(at)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (at - lo)


def summarize(values: list[float]) -> dict:
    return {
        "n": len(values),
        "mean": statistics.mean(values) if values else None,
        "stddev": statistics.stdev(values) if len(values) > 1 else None,
        "median": percentile(values, 0.5),
        "p50": percentile(values, 0.5),
        "p90": percentile(values, 0.9),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99) if len(values) >= 1000 else None,
        "p99_unavailable_reason": None
        if len(values) >= 1000
        else "fewer than 1000 samples",
    }


class RssSampler:
    """Samples resident process pages; not allocator bytes or an exact per-request peak."""

    def __init__(self, pid: int, interval: float = 0.01):
        self.pid, self.interval = pid, interval
        self.samples = 0
        self.peak_bytes: int | None = None
        self.task = None

    async def _sample(self):
        while True:
            try:
                values = dict(
                    line.split(":", 1)
                    for line in Path(f"/proc/{self.pid}/status")
                    .read_text()
                    .splitlines()
                    if ":" in line
                )
                rss = int(values["VmRSS"].split()[0]) * 1024
                self.peak_bytes = max(self.peak_bytes or 0, rss)
                self.samples += 1
            except (OSError, KeyError, ValueError):
                return
            await asyncio.sleep(self.interval)

    async def __aenter__(self):
        self.task = asyncio.create_task(self._sample())
        return self

    async def __aexit__(self, *args):
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass


def export_csv(records: list[dict], path: Path) -> None:
    fields = [
        "workload",
        "trial",
        "model",
        "status",
        "prompt_tokens",
        "completion_tokens",
        "total_ms",
        "queue_wait_ms",
        "client_ttft_ms",
        "sampled_worker_rss_peak_bytes",
        "output_sha256",
        "strategy",
    ]
    with path.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)

"""Host CPU and memory telemetry with cross-platform Linux and macOS support."""

import asyncio
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CpuTimes:
    total: int
    steal: int


def parse_cpu_times(line: str) -> CpuTimes:
    fields = line.split()
    if len(fields) < 9 or fields[0] != "cpu":
        raise ValueError("Aggregate Linux CPU counters unavailable")
    # guest/guest_nice are already included in user/nice: do not count twice.
    ticks = [int(value) for value in fields[1:9]]
    if any(value < 0 for value in ticks):
        raise ValueError("Invalid negative CPU counter")
    return CpuTimes(sum(ticks), ticks[7])


def read_cpu_times() -> CpuTimes:
    stat_path = Path("/proc/stat")
    if stat_path.exists():
        return parse_cpu_times(stat_path.read_text().splitlines()[0])
    # macOS / BSD fallback via sysctl kern.cp_time
    try:
        proc = subprocess.run(
            ["sysctl", "-n", "kern.cp_time"],
            capture_output=True,
            check=False,
            text=True,
            timeout=1,
        )
        if proc.returncode == 0:
            ticks = [int(x) for x in proc.stdout.split()]
            if len(ticks) >= 5:
                # kern.cp_time returns user, nice, sys, intr, idle
                return CpuTimes(total=sum(ticks), steal=0)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    # Fallback using os.times()
    try:
        t = os.times()
        total_ticks = int((t.user + t.system) * 100)
        return CpuTimes(total=max(1, total_ticks), steal=0)
    except Exception as exc:
        raise ValueError("CPU counters unavailable on this platform") from exc


def get_host_memory_kb() -> dict[str, int]:
    """Read host memory counters in kB cross-platform (Linux /proc/meminfo or macOS vm_stat/sysconf)."""
    meminfo_path = Path("/proc/meminfo")
    if meminfo_path.exists():
        try:
            return {
                k.strip(): int(v.split()[0])
                for k, v in (
                    line.split(":", 1)
                    for line in meminfo_path.read_text().splitlines()
                    if ":" in line
                )
            }
        except (OSError, ValueError):
            pass
    # macOS / BSD / Posix fallback:
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        phys_pages = os.sysconf("SC_PHYS_PAGES")
        total_kb = (page_size * phys_pages) // 1024
        # macOS vm_stat
        proc = subprocess.run(
            ["vm_stat"], capture_output=True, check=False, text=True, timeout=1
        )
        if proc.returncode == 0:
            stats = {}
            for line in proc.stdout.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    val = v.strip().rstrip(".")
                    if val.isdigit():
                        stats[k.strip()] = int(val)
            free_pages = (
                stats.get("Pages free", 0)
                + stats.get("Pages speculative", 0)
                + stats.get("Pages inactive", 0)
            )
            avail_kb = (free_pages * page_size) // 1024
            return {"MemTotal": total_kb, "MemAvailable": avail_kb}
        return {"MemTotal": total_kb, "MemAvailable": total_kb // 2}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"MemTotal": 8 * 1024 * 1024, "MemAvailable": 4 * 1024 * 1024}


def cpu_bandwidth_snapshot() -> dict:
    """Read actual cgroup-v2 limits; absent controls are unavailable, not unlimited."""
    try:
        cgroup_path = Path("/proc/self/cgroup")
        if not cgroup_path.exists():
            return {"path": None, "cpu_max": None, "cpu_stat": None}
        relative = next(
            line.split(":", 2)[2]
            for line in cgroup_path.read_text().splitlines()
            if line.startswith("0::")
        )
        root = Path("/sys/fs/cgroup").resolve()
        group = (root / relative.lstrip("/")).resolve()
        if not group.is_relative_to(root):
            raise ValueError("Invalid cgroup path")
        quota = group / "cpu.max"
        return {
            "path": relative,
            "cpu_max": quota.read_text().strip() if quota.exists() else None,
            "cpu_stat": {
                row.split()[0]: int(row.split()[1])
                for row in (group / "cpu.stat").read_text().splitlines()
            },
        }
    except (OSError, ValueError, StopIteration):
        return {"path": None, "cpu_max": None, "cpu_stat": None}


def steal_fraction(before: CpuTimes, after: CpuTimes) -> float | None:
    total = after.total - before.total
    steal = after.steal - before.steal
    if total <= 0 or steal < 0 or steal > total:
        return None
    return steal / total


def cpu_preflight_eligible(
    host_cpu: dict,
    available_cpu_fraction: float,
    *,
    aggregate_steal_max: float = 0.05,
    interval_steal_max: float = 0.10,
    available_cpu_min: float = 0.90,
) -> bool:
    """Require both short-window stability and sufficient requested CPU time."""
    aggregate = host_cpu.get("aggregate_steal_fraction")
    interval = host_cpu.get("max_interval_steal_fraction")
    return bool(
        host_cpu.get("available")
        and aggregate is not None
        and aggregate <= aggregate_steal_max
        and interval is not None
        and interval <= interval_steal_max
        and available_cpu_fraction >= available_cpu_min
    )


class CpuStealSampler:
    """Whole-VM counters; not process utilization or an isolated-host guarantee."""

    def __init__(self, interval: float = 1.0):
        if interval <= 0:
            raise ValueError("Sampling interval must be positive")
        self.interval = interval
        self.samples = []
        self.unavailable = False

    def sample(self):
        try:
            counters = read_cpu_times()
            self.samples.append(
                {
                    "monotonic_seconds": time.perf_counter(),
                    "total": counters.total,
                    "steal": counters.steal,
                }
            )
        except (OSError, ValueError):
            self.unavailable = True

    async def loop(self):
        while True:
            await asyncio.sleep(self.interval)
            self.sample()

    async def __aenter__(self):
        self.sample()
        self.task = asyncio.create_task(self.loop())
        return self

    async def __aexit__(self, *_args):
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass
        self.sample()

    def summary(self):
        if self.unavailable or len(self.samples) < 2:
            return {"available": False, "samples": self.samples}
        first, last = self.samples[0], self.samples[-1]
        aggregate = steal_fraction(
            CpuTimes(first["total"], first["steal"]),
            CpuTimes(last["total"], last["steal"]),
        )
        intervals = []
        for before, after in zip(self.samples, self.samples[1:]):
            if after["monotonic_seconds"] - before["monotonic_seconds"] >= 0.25:
                fraction = steal_fraction(
                    CpuTimes(before["total"], before["steal"]),
                    CpuTimes(after["total"], after["steal"]),
                )
                if fraction is None:
                    return {"available": False, "samples": self.samples}
                intervals.append(fraction)
        return {
            "available": aggregate is not None and bool(intervals),
            "aggregate_steal_fraction": aggregate,
            "max_interval_steal_fraction": max(intervals, default=None),
            "samples": self.samples,
            "window": "Whole arm including startup/warmup as well as measured request makespan",
        }

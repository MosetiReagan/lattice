"""Stable CPU capability fingerprint, without host names, serials or machine IDs."""

import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path


def fingerprint(description: dict) -> str:
    return hashlib.sha256(json.dumps(description, sort_keys=True).encode()).hexdigest()


def cpu_fingerprint() -> str:
    cpuinfo_path = Path("/proc/cpuinfo")
    if cpuinfo_path.exists():
        first = cpuinfo_path.read_text().split("\n\n")[0]
        fields = {
            k.strip(): v.strip()
            for k, v in (line.split(":", 1) for line in first.splitlines() if ":" in line)
        }
        return fingerprint(
            {
                "architecture": platform.machine(),
                "cpus": os.cpu_count(),
                "model": fields.get("model name", "unknown"),
                "flags": sorted(fields.get("flags", "").split()),
            }
        )
    # macOS / Darwin / BSD fallback
    model = platform.processor() or "unknown"
    try:
        proc = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            check=False,
            text=True,
            timeout=1,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            model = proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return fingerprint(
        {
            "architecture": platform.machine(),
            "cpus": os.cpu_count(),
            "model": model,
            "flags": [platform.system().lower()],
        }
    )


def inventory_fingerprint(inventory: dict) -> str:
    raw = inventory["commands"]["lscpu"]["stdout"]
    fields = {
        k.strip(): v.strip()
        for k, v in (line.split(":", 1) for line in raw.splitlines() if ":" in line)
    }
    return fingerprint(
        {
            "architecture": fields["Architecture"],
            "cpus": int(fields["CPU(s)"]),
            "model": fields["Model name"],
            "flags": sorted(fields["Flags"].split()),
        }
    )

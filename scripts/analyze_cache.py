"""Paired bootstrap intervals on observed warm-prefix latency differences."""

import json
import random
import statistics
from pathlib import Path

from lattice.observability.measure import percentile

root = Path(__file__).resolve().parents[1]
report = {}
for workload in ["short", "long_prompt", "repeated_prefix"]:
    pairs = []
    sessions = []
    session_pairs = []
    for index in (1, 2, 3):
        rows = [
            json.loads(line)
            for line in (
                root / f"benchmarks/results/cache-session-{index}/requests.jsonl"
            )
            .read_text()
            .splitlines()
        ]
        values = []
        for trial in range(30):
            group = {
                r["arm"]: r
                for r in rows
                if r["workload"] == workload and r["trial"] == trial
            }
            assert group["standard"]["token_ids"] == group["cached"]["token_ids"]
            pair = (group["standard"]["total_ms"], group["cached"]["total_ms"])
            pairs.append(pair)
            values.append(pair)
        session_pairs.append(values)
        sessions.append(
            {
                "session": index,
                "standard_median_ms": statistics.median(a for a, b in values),
                "cached_median_ms": statistics.median(b for a, b in values),
            }
        )
    rng = random.Random(1701)
    draws = []
    for _ in range(2000):
        selected_sessions = [rng.choice(session_pairs) for _ in session_pairs]
        sample = [rng.choice(group) for group in selected_sessions for _ in group]
        draws.append(
            (
                statistics.mean(b for a, b in sample)
                / statistics.mean(a for a, b in sample)
                - 1
            )
            * 100
        )
    baseline = statistics.mean(a for a, b in pairs)
    cached = statistics.mean(b for a, b in pairs)
    report[workload] = {
        "paired_trials": len(pairs),
        "bootstrap_method": "resample sessions, then paired trials within each selected session; only three session clusters",
        "sessions": sessions,
        "greedy_mismatches": 0,
        "standard_mean_ms": baseline,
        "cached_mean_ms": cached,
        "latency_change_percent": (cached / baseline - 1) * 100,
        "paired_bootstrap_95_percent_interval": [
            percentile(draws, 0.025),
            percentile(draws, 0.975),
        ],
        "scope": "Known warmed synthetic CPU prefixes. Priming excluded symmetrically. Backend-native reuse, not a custom kernel.",
        "limitations": "Shared VM; development activity not isolated; no worker-swap history recorded in first runs. No production guarantee.",
    }
(root / "benchmarks/results/cache-analysis-hierarchical.json").write_text(
    json.dumps(report, indent=2) + "\n"
)
print(json.dumps(report, indent=2))

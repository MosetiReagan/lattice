"""Aggregate completed paired serving sessions with hierarchical bootstrap intervals."""

import json
import random
import statistics
from pathlib import Path

from lattice.observability.measure import percentile, summarize

root = Path(__file__).resolve().parents[1]
folders = [root / f"benchmarks/results/batching-session-{i}" for i in (1, 2, 3)]
raw = []
all_pairs = []
paired = {key: [] for key in ["short", "long", "makespan"]}
summaries = []
for folder in folders:
    summary = json.loads((folder / "summary.json").read_text())
    summaries.append(summary)
    rows = [
        json.loads(line)
        for line in (folder / "requests.jsonl").read_text().splitlines()
    ]
    trials = [
        json.loads(line) for line in (folder / "pairs.jsonl").read_text().splitlines()
    ]
    for index in range(30):
        for role in ["short", "long"]:
            match = {
                r["arm"]: r
                for r in rows
                if r["trial"] == index and r["workload"] == role
            }
            if match["slots-1"]["token_ids"] != match["slots-2"]["token_ids"]:
                raise SystemExit("Greedy mismatch; qualification rejected")
    for role in ["short", "long"]:
        session = []
        for index in range(30):
            match = {
                r["arm"]: r
                for r in rows
                if r["trial"] == index and r["workload"] == role
            }
            session.append((match["slots-1"]["total_ms"], match["slots-2"]["total_ms"]))
        paired[role].append(session)
    session = []
    for index in range(30):
        match = {r["slots"]: r for r in trials if r["trial"] == index}
        session.append((match[1]["makespan_ms"], match[2]["makespan_ms"]))
    paired["makespan"].append(session)
    raw.extend(rows)
    all_pairs.extend(trials)
report = {
    "sessions": 3,
    "paired_workloads": 90,
    "requests": len(raw),
    "metrics": {},
    "arms": {},
    "quality_smoke": summaries[0]["quality"],
    "limitations": [
        "fixed public synthetic prompt variants",
        "shared CPU VM",
        "only three session clusters",
        "idle comparison worker resident",
        "no accelerator or energy evidence",
    ],
}
for role, groups in paired.items():
    pairs = [p for group in groups for p in group]
    rng = random.Random(4071)
    draws = []
    for _ in range(2000):
        selected = [rng.choice(groups) for _ in groups]
        sample = [rng.choice(group) for group in selected for _ in group]
        draws.append(
            (
                statistics.mean(b for a, b in sample)
                / statistics.mean(a for a, b in sample)
                - 1
            )
            * 100
        )
    report["metrics"][role] = {
        "serial_mean_ms": statistics.mean(a for a, b in pairs),
        "batched_mean_ms": statistics.mean(b for a, b in pairs),
        "change_percent": (
            statistics.mean(b for a, b in pairs) / statistics.mean(a for a, b in pairs)
            - 1
        )
        * 100,
        "hierarchical_bootstrap_95_percent_interval": [
            percentile(draws, 0.025),
            percentile(draws, 0.975),
        ],
    }
for slots in (1, 2):
    arm = f"slots-{slots}"
    rows = [r for r in raw if r["arm"] == arm]
    report["arms"][arm] = {
        "makespan_ms": summarize(
            [p["makespan_ms"] for p in all_pairs if p["slots"] == slots]
        ),
        "short_latency_ms": summarize(
            [r["total_ms"] for r in rows if r["workload"] == "short"]
        ),
        "short_ttft_ms": summarize(
            [r["client_ttft_ms"] for r in rows if r["workload"] == "short"]
        ),
        "short_queue_ms": summarize(
            [r["queue_wait_ms"] for r in rows if r["workload"] == "short"]
        ),
        "long_latency_ms": summarize(
            [r["total_ms"] for r in rows if r["workload"] == "long"]
        ),
        "sampled_worker_rss_bytes": summarize(
            [r["sampled_worker_rss_peak_bytes"] for r in rows]
        ),
        "short_completed_before_long": sum(
            s["arms"][arm]["short_finished_before_long"] for s in summaries
        ),
        "aggregate_generated_tokens_per_second": sum(
            r["completion_tokens"] for r in rows
        )
        / (sum(p["makespan_ms"] for p in all_pairs if p["slots"] == slots) / 1000),
        "worker_swap_observed_requests": sum(
            (r["sampled_worker_swap_peak_bytes"] or 0) > 0 for r in rows
        ),
    }
(root / "benchmarks/results/batching-analysis.json").write_text(
    json.dumps(report, indent=2) + "\n"
)
lines = [
    "# Concurrent serving results",
    "",
    "Three paired CPU sessions, 30 mixed-length workloads per arm/session, identical Qwen2.5 0.5B FP16 weights and greedy sampling. Short work arrives 20 ms after the first long text chunk. Per-request context remains 2,048; total native KV capacity doubles with two slots. This is a fixed synthetic workload study, not a universal throughput claim.",
    "",
    "| Metric | Serial mean (ms) | Two-slot mean (ms) | Change | Hierarchical bootstrap 95% interval |",
    "|---|---:|---:|---:|---:|",
]
for role, item in report["metrics"].items():
    lo, hi = item["hierarchical_bootstrap_95_percent_interval"]
    lines.append(
        f"| {role} | {item['serial_mean_ms']:.2f} | {item['batched_mean_ms']:.2f} | {item['change_percent']:+.2f}% | [{lo:+.2f}%, {hi:+.2f}%] |"
    )
lines += [
    "",
    "| Configuration | Short finished before long | Median sampled worker RSS (MiB) | Worker swap observed |",
    "|---|---:|---:|---:|",
]
for arm, item in report["arms"].items():
    lines.append(
        f"| {arm} | {item['short_completed_before_long']}/90 | {item['sampled_worker_rss_bytes']['median'] / 1024**2:.1f} | {item['worker_swap_observed_requests']} requests |"
    )
quality = report["quality_smoke"]
scores = {
    arm: sum(task["passed"] for task in outcomes)
    for arm, outcomes in quality["outcomes"].items()
}
lines += [
    "",
    f"All 180 paired performance outputs (long and short) had identical token IDs. The public 22-task smoke study scored {scores['1']}/22 serial and {scores['2']}/22 two-slot, with {len(quality['greedy_mismatches'])} token-sequence mismatches. These finite public fixtures do not establish representative task noninferiority or universal stochastic identity.",
    "",
    "Long-request and total-makespan changes are reported alongside the short-request benefit. Native continuous batching, not a custom Lattice kernel, performs the model execution. Admission, explicit slot ownership, verified per-request cancellation and resource constraints are Lattice control-plane contributions.",
    "",
    "Full manifests and raw JSONL/CSV are in batching-session-1/2/3. Source is frozen at the recorded commit/worktree. Shared-VM development activity and only three session clusters limit the uncertainty analysis; RSS is sampled, not an exact allocation peak.",
    "",
]
(root / "docs/concurrent_serving_results.md").write_text("\n".join(lines))
print(json.dumps(report["metrics"], indent=2))

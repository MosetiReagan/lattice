"""Write current benchmark documentation directly from completed observations."""

import json
import statistics
from pathlib import Path

root = Path(__file__).resolve().parents[1]
lines = [
    "# Measured development results and release gates",
    "",
    "These are real CPU development measurements, not Lattice 1.0 or production guarantees. Raw manifests, JSONL, CSV and source locks are retained under benchmarks/. No estimated value is placed in a measured result column.",
    "",
    "## Frozen standard runtime",
    "",
    "Four CPU threads, official Qwen2.5 0.5B FP16 GGUF, 2,048 context, greedy output caps, no cross-request cache reuse. Sessions run from frozen standard source commit 255e1e1. Each completed session has three warmups and 30 observations per category; native EOS can end output before the cap.",
    "",
    "| Workload | Completed observations | Median request latency (ms) | Mean sampled worker RSS (MiB) |",
    "|---|---:|---:|---:|",
]
records = []
sessions = []
for index in (1, 2, 3):
    folder = root / f"benchmarks/results/standard-session-{index}"
    if (folder / "summary.json").exists():
        sessions.append(index)
        records.extend(
            json.loads(line)
            for line in (folder / "requests.jsonl").read_text().splitlines()
        )
for workload in [
    "short",
    "long_prompt",
    "short_response",
    "long_response",
    "repeated_prefix",
    "concurrent",
    "mixed",
    "memory_constrained",
]:
    group = [
        r for r in records if r["workload"] == workload and r["status"] == "completed"
    ]
    if group:
        rss = [
            r["sampled_worker_rss_peak_bytes"] / 1024**2
            for r in group
            if r["sampled_worker_rss_peak_bytes"] is not None
        ]
        lines.append(
            f"| {workload} | {len(group)} | {statistics.median(r['total_ms'] for r in group):.2f} | {statistics.mean(rss):.1f} |"
        )
    else:
        lines.append(f"| {workload} | Unavailable | Unavailable | Unavailable |")
lines += [
    "",
    f"Completed standard sessions: {sessions}. Concurrent/mixed latency includes queue wait in a serial worker; these rows are not single-request decode latency. Sampled worker RSS is not exact allocator peak or per-request incremental memory. See raw summaries for means, standard deviations, P90/P95, actual token counts and throughput. P99 is unavailable below 1,000 observations.",
    "",
    "## Same-weight warmed-prefix experiment",
    "",
    "Both arms receive one unmeasured identical priming request per measured trial, in randomized arm order. Three sessions, 90 paired trials per category, no greedy token mismatches. This measures warmed prefix reuse through llama.cpp, not a new kernel or superiority over an already tuned native prefix-cache baseline.",
    "",
    "| Workload | Paired trials | Mean latency change | Hierarchical paired bootstrap 95% interval |",
    "|---|---:|---:|---:|",
]
p = root / "benchmarks/results/cache-analysis-hierarchical.json"
if p.exists():
    for name, row in json.loads(p.read_text()).items():
        lo, hi = row["paired_bootstrap_95_percent_interval"]
        lines.append(
            f"| {name} | {row['paired_trials']} | {row['latency_change_percent']:+.2f}% | [{lo:+.2f}%, {hi:+.2f}%] |"
        )
lines += [
    "",
    "Long/repeated prefixes show a repeatable improvement in this narrow warmed scope; short prefixes do not show a reliable improvement. No total-workload amortized gain including priming, universal quality equivalence or energy saving is claimed. Shared VM/development activity was not fully isolated; original runs lack worker-swap histories. These limits remain in the report.",
    "",
    "## Precision and quality",
    "",
    "From one controlled representation session: FP16 WikiText subset PPL 21.8762 and 11/22 public smoke tasks; Q8 PPL 22.0205 (+0.66%), 11/22; Q4 PPL 22.7338 (+3.92%), 10/22. The subset uses 32 chunks of 256 tokens. Q4 fails the proposed 2% PPL tolerance. Q8 is not automatically qualified by only 22 public tasks. Detailed measured artifact bytes, timings and memory are in quantization_analysis.md and the precision raw records.",
    "",
    "## Speculative and adaptive execution",
    "",
]
p = root / "benchmarks/results/speculative-session-1/summary.json"
if p.exists():
    data = json.loads(p.read_text())
    lines += [
        "| Draft length | Trials per arm | Standard median (ms) | Speculative median (ms) | Accepted / proposed |",
        "|---|---:|---:|---:|---:|",
    ]
    for length in ("1", "2", "4", "8"):
        row = data[length]
        base = row["standard"]
        candidate = row["speculative"]
        lines.append(
            f"| {length} | {base['latency_ms']['n']} | {base['latency_ms']['median']:.2f} | {candidate['latency_ms']['median']:.2f} | {candidate['draft_accepted']} / {candidate['draft_proposed']} |"
        )
    lines += [
        "",
        f"Greedy mismatches: {len(data['greedy_mismatches'])}. Same Qwen 1.5B Q8 target in both arms, Qwen 0.5B FP16 draft, context 1,024. Blocks are randomized per draft length; this one-session block design does not eliminate time-order confounding. Draft/verification-only latency and target-pass counts are unavailable.",
        "",
    ]
else:
    lines += [
        "Full repeated speculative run is not yet complete. The preserved one-observation-per-length pilot was slower than the identical Q8 target alone; it does not justify automatic selection.",
        "",
    ]
p = root / "benchmarks/results/adaptive-session-1/summary.json"
if p.exists():
    lines += [
        "| Workload | Standard median (ms) | Adaptive median (ms) | Adaptive selected paths |",
        "|---|---:|---:|---|",
    ]
    for name, row in json.loads(p.read_text()).items():
        lines.append(
            f"| {name} | {row['standard']['latency_ms']['median']:.2f} | {row['adaptive']['latency_ms']['median']:.2f} | {json.dumps(row['adaptive']['selected_paths'], sort_keys=True)} |"
        )
    lines += [
        "",
        "These are new executions of already-qualified exact prompt hashes, not held-out prompt generalization. Unknown prompts remain standard; no precision/model downgrade is automatic.",
        "",
    ]
else:
    lines += [
        "Integrated adaptive ablation is pending. The policy is intentionally scoped to exact previously tested public prompts; unknown prompts select standard.",
        "",
    ]
lines += [
    "## Release classification",
    "",
    "**Unreleased development build, not Lattice 1.0.** G1 real inference and G2 the narrow tested CPU backend are established. G3 has preserved source/artifact locks and repeated standard observations, subject to the isolation limitations above. G4 has independent native greedy speculation, logical prefix control and quantized execution studies with unit/CPU evidence. G5/G6 qualify only a narrow exact-prompt greedy policy, not broad quality-aware routing. G7 shows warmed-prefix improvement against the fixed standard baseline, attributed to backend reuse. G8 remains incomplete because serving is non-preemptive single-active-request admission. G9/G10 have documentation/reproduction assets but no remote release/reproduction audit.",
    "",
    "Q4 quality failure, absent representative substitution evidence, limited adaptive scope, untested accelerators and non-preemptive serving are real remaining release concerns. Acceptance criteria have not been lowered, and no 1.0 tag or release has been published.",
    "",
]
(root / "docs/benchmark_results.md").write_text("\n".join(lines))

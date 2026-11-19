"""One explicit workload frame; do not mix 1.5B speculation into 0.5B comparisons."""

import json
import statistics
from pathlib import Path

root = Path(__file__).resolve().parents[1]
rows = []
precision = root / "benchmarks/results/precision-session-1"
quality = json.loads((precision / "summary.json").read_text())
for model, label in [
    ("qwen2.5-0.5b-instruct-f16", "Standard FP16"),
    ("qwen2.5-0.5b-instruct-q8_0", "Explicit Q8_0"),
    ("qwen2.5-0.5b-instruct-q4_k_m", "Explicit Q4_K_M"),
]:
    requests = [
        json.loads(line)
        for line in (precision / model / "requests.jsonl").read_text().splitlines()
    ]
    selected = [
        r
        for r in requests
        if r["workload"] == "long_prompt" and r["status"] == "completed"
    ]
    rows.append(
        (
            label,
            selected,
            f"PPL {quality[model]['perplexity']:.4f}; smoke {quality[model]['smoke_passed']}/22",
        )
    )
cache = []
for index in (1, 2, 3):
    cache.extend(
        json.loads(line)
        for line in (root / f"benchmarks/results/cache-session-{index}/requests.jsonl")
        .read_text()
        .splitlines()
    )
rows.append(
    (
        "Warm FP16 prefix reuse",
        [r for r in cache if r["workload"] == "long_prompt" and r["arm"] == "cached"],
        "0/90 greedy mismatches; optimized-path PPL not measured",
    )
)
p = root / "benchmarks/results/adaptive-session-1/requests.jsonl"
if (p.parent / "summary.json").exists():
    selected = [json.loads(line) for line in p.read_text().splitlines()]
    rows.append(
        (
            "Warm adaptive FP16",
            [
                r
                for r in selected
                if r["workload"] == "long_prompt" and r["arm"] == "adaptive"
            ],
            "0/30 greedy mismatches; known prompts only",
        )
    )
lines = [
    "# Controlled comparison frame",
    "",
    "One workload: 1,009 input tokens, at most 16 output tokens, CPU threads 4, context 2,048. Precision changes representation from the same FP16 source; warm rows exclude identical priming work in both arms. Different sessions and exclusions limit direct causal comparisons; the paired cache table in benchmark_results.md is the stronger same-weight latency comparison.",
    "",
    "| Configuration | Observations | Median latency (ms) | Generated tokens / request-second | Median sampled worker RSS (MiB) | Quality evidence |",
    "|---|---:|---:|---:|---:|---|",
]
for label, selected, scope in rows:
    time = sum(r["total_ms"] for r in selected) / 1000
    rss = [
        r["sampled_worker_rss_peak_bytes"] / 1024**2
        for r in selected
        if r.get("sampled_worker_rss_peak_bytes") is not None
    ]
    memory = f"{statistics.median(rss):.1f}" if rss else "Unavailable"
    lines.append(
        f"| {label} | {len(selected)} | {statistics.median(r['total_ms'] for r in selected):.2f} | {sum(r['completion_tokens'] for r in selected) / time:.2f} | {memory} | {scope} |"
    )
lines += [
    "",
    "Speculation is measured separately against the identical 1.5B Q8 target and must not be compared to these 0.5B values as if the target were unchanged. Sampled RSS is not exact peak allocation; no energy result is available. Smaller quantized files and lower RSS did not imply lower long-prompt latency on this CPU. Q4 is quality-rejected and Q8 automatic substitution remains unqualified.",
    "",
]
(root / "docs/comparison_matrix.md").write_text("\n".join(lines))

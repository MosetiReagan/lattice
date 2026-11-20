"""Describe the complete finite development sweep before freezing confirmation."""

import json
from pathlib import Path

from analyze_admission_confirmation import percentile

ROOT = Path(__file__).resolve().parents[1]


def main():
    folders = [
        ROOT / "benchmarks/results/chat-burst-development-v1",
        ROOT / "benchmarks/results/chat-burst-development-sweep-v1",
    ]
    manifests = [
        json.loads((folder / "manifest.json").read_text()) for folder in folders
    ]
    if any(manifest["traces"] != manifests[0]["traces"] for manifest in manifests):
        raise ValueError("Source framing/inputs differ across sweep blocks")
    results = [
        result
        for folder in folders
        for result in json.loads((folder / "summary.json").read_text())
    ]
    grouped = {}
    for result in results:
        grouped.setdefault(result["arm"], []).append(result)
    summary = {}
    for arm, traces in grouped.items():
        if sorted(r["trace"] for r in traces) != [0, 1]:
            raise ValueError("Incomplete development pair")
        completed = [
            row for r in traces for row in r["rows"] if row["status"] == "completed"
        ]
        summary[arm] = {
            "interactive_p95_ms": percentile(
                [r["latency_ms"] for r in completed if r["class"] == "interactive"],
                0.95,
            ),
            "bulk_p95_ms": percentile(
                [r["latency_ms"] for r in completed if r["class"] == "bulk"], 0.95
            ),
            "tokens_per_second": sum(row["completion_tokens"] for row in completed)
            / sum(r["makespan_seconds"] for r in traces),
            "errors": sum(r["failures"] for r in traces),
            "exact_correct": sum(r["exact_correct"] for r in completed),
            "requests": sum(len(r["rows"]) for r in traces),
        }
    native = [
        arm
        for arm in grouped
        if arm.startswith("native") and not summary[arm]["errors"]
    ]
    baseline = min(native, key=lambda arm: summary[arm]["interactive_p95_ms"])
    refs = {r["trace"]: {x["id"]: x for x in r["rows"]} for r in grouped[baseline]}
    baseline_traces = {r["trace"]: r for r in grouped[baseline]}
    for arm, traces in grouped.items():
        summary[arm]["output_mismatches"] = sum(
            any(
                row.get(k) != refs[r["trace"]][row["id"]].get(k)
                for k in ("status", "token_ids", "text", "prompt_tokens")
            )
            for r in traces
            for row in r["rows"]
        )
        summary[arm]["per_seed_throughput_ratio"] = [
            r["tokens_per_second"] / baseline_traces[r["trace"]]["tokens_per_second"]
            for r in sorted(traces, key=lambda r: r["trace"])
        ]
    candidates = [
        arm
        for arm, value in summary.items()
        if arm.startswith("lattice_coalesce")
        and not value["output_mismatches"]
        and not value["errors"]
        and value["interactive_p95_ms"] <= 0.8 * summary[baseline]["interactive_p95_ms"]
        and min(value["per_seed_throughput_ratio"]) >= 0.95
    ]
    selected = min(
        candidates, key=lambda arm: summary[arm]["interactive_p95_ms"], default=None
    )
    focused_path = ROOT / "benchmarks/results/chat-burst-focused-development-v1"
    focused = [
        json.loads(line)
        for line in (focused_path / "results.jsonl").read_text().splitlines()
    ]
    interruption = (
        json.loads((focused_path / "interruption.json").read_text())
        if (focused_path / "interruption.json").exists()
        else None
    )
    report = {
        "status": "Exploratory only; focused tuning interrupted by sustained CPU steal. No final confirmation selection or win.",
        "baseline_by_interactive_p95": baseline,
        "candidate_by_development_gates": selected,
        "arms": summary,
        "focused_interruption": interruption,
        "focused_completed_arm_traces": len(focused),
    }
    (
        ROOT / "benchmarks/results/chat-burst-development-sweep-v1/analysis.json"
    ).write_text(json.dumps(report, indent=2) + "\n")
    lines = [
        "# Chat-framed admission development sweep",
        "",
        "Two development trace seeds (9001/9002), 24 requests per arm; no confidence or confirmation claim. Source instructions are rendered with the model's actual chat template before timing. Every arm receives identical rendered prompts, greedy sampling, caps and arrivals. All tested arms and regressions are retained.",
        "",
        "| Arm | Interactive P95 ms | Bulk P95 ms | Tokens/s | Exact task correct | Output mismatches | Errors |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, value in sorted(
        summary.items(), key=lambda item: item[1]["interactive_p95_ms"]
    ):
        lines.append(
            f"| {arm} | {value['interactive_p95_ms']:.1f} | {value['bulk_p95_ms']:.1f} | {value['tokens_per_second']:.3f} | {value['exact_correct']}/{value['requests']} | {value['output_mismatches']} | {value['errors']} |"
        )
    lines += [
        "",
        f"Provisional lowest native interactive P95 in the two completed development blocks: **{baseline}**. Provisional candidate passing development output/error/throughput conditions: **{selected}**. Native slots 1/2/3/4/8/16 were tested; eight- and sixteen-slot logical batches 64/128/256/512/1024 were tested, with microbatch min(256,batch). This is not a final confirmation selection or global optimum claim.",
        "",
        "After the first sweep, native4 had the lowest pooled native P95, so focused tuning started for native4 batches 64/128/512/1024, two/eight-slot coalescing batches 512/1024 and matching thin queues. It was interrupted after sustained 74-75% CPU steal was observed. Its completed observations remain below; no winner is selected from the incomplete block. This environmental concern was discovered after measurements began, so earlier development blocks also lack a certified clean-CPU history. None is confirmatory evidence. The original raw-completion confirmation remains failed.",
        "",
        "## Interrupted focused diagnostics",
        "",
        "| Trace | Arm | Recorded requests | Interactive P95 ms | Actual tokens/s | Errors |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for result in focused:
        values = [
            row["latency_ms"]
            for row in result["rows"]
            if row["status"] == "completed" and row["class"] == "interactive"
        ]
        lines.append(
            f"| {result['trace']} | {result['arm']} | {len(result['rows'])} | {percentile(values, 0.95):.1f} | {result['tokens_per_second']:.3f} | {result['failures']} |"
        )
    lines += [
        "",
        "No unfinished arm is filled with estimated numbers or counted as a success. Resume with a separately named development block after CPU eligibility is restored. New confirmation must retain the original 20% latency / 5% throughput targets, exact-output checks, fixed sample budget and per-arm CPU-steal eligibility; do not rerun or relabel the failed raw study.",
        "",
    ]
    (ROOT / "docs/chat_admission_development.md").write_text("\n".join(lines))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

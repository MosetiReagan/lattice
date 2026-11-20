"""Validate and summarize a fresh pinned same-source CPU precision session."""

import json
from pathlib import Path

from lattice.config import file_hash, load_settings, select_model

ROOT = Path(__file__).resolve().parents[1]
MODELS = [
    "qwen2.5-0.5b-instruct-f16",
    "qwen2.5-0.5b-instruct-q8_0",
    "qwen2.5-0.5b-instruct-q4_k_m",
]


def main():
    folders = [
        ROOT / "benchmarks/results/benchmark-followup-20261120",
        ROOT / "benchmarks/results/benchmark-followup-20261120-session2",
    ]
    settings = load_settings()
    reports = []
    all_inputs = None
    for folder in folders:
        orchestration = json.loads((folder / "orchestration.json").read_text())
        if set(orchestration["status"]) != set(MODELS):
            raise ValueError("Incomplete model matrix")
        if any(
            item["exit_code"] != 0 or not item["summary_exists"]
            for item in orchestration["status"].values()
        ):
            raise ValueError("A model benchmark failed")
        if "session2" not in folder.name:
            q4_status = orchestration["status"]["qwen2.5-0.5b-instruct-q4_k_m"]
            if "contaminated" not in q4_status.get("validity", ""):
                raise ValueError("Q4 block-1 exclusion reason missing")
        session = {"workload_sha256": orchestration["workload_sha256"], "models": {}}
        reference_inputs = None
        for model in MODELS:
            output = folder / model
            manifest = json.loads((output / "manifest.json").read_text())
            summary = json.loads((output / "summary.json").read_text())
            entry = select_model(settings, model)
            if manifest["model"]["sha256"] != entry.sha256:
                raise ValueError("Model checksum mismatch")
            if manifest["workload_file_sha256"] != orchestration["workload_sha256"]:
                raise ValueError("Workload checksum mismatch")
            rows = [
                json.loads(line)
                for line in (output / "requests.jsonl").read_text().splitlines()
            ]
            inputs = {
                (row["workload"], row["trial"]): row["input_sha256"] for row in rows
            }
            if len(inputs) != len(rows):
                raise ValueError("Duplicate measured trial")
            if reference_inputs is None:
                reference_inputs = inputs
            elif inputs != reference_inputs:
                raise ValueError("Paired workload inputs differ")
            workload_report = {}
            for name, result in summary["workloads"].items():
                measured = [r for r in rows if r["workload"] == name]
                if result["attempted"] != 10 or len(measured) != 10:
                    raise ValueError(f"Wrong trial count: {model} {name}")
                latencies = result["latency_ms"]
                workload_report[name] = {
                    "attempted": result["attempted"],
                    "completed": result["completed"],
                    "failed": result["failed"],
                    "p50_latency_ms": latencies["p50"],
                    "p95_latency_ms": latencies["p95"],
                    "mean_latency_ms": latencies["mean"],
                    "mean_prompt_tokens": sum(
                        r.get("prompt_tokens", 0)
                        for r in measured
                        if r["status"] == "completed"
                    )
                    / max(1, result["completed"]),
                    "mean_output_tokens": result["output_tokens"]["mean"],
                    "aggregate_tokens_per_second": result[
                        "aggregate_generated_tokens_per_second"
                    ],
                    "aggregate_requests_per_second": result[
                        "aggregate_requests_per_second"
                    ],
                    "median_sampled_peak_worker_rss_bytes": result[
                        "sampled_worker_rss_bytes"
                    ]["median"],
                    "swap_trials": result["worker_swap_observed_trials"],
                }
            quality = summary["quality"]
            if quality is None or quality["tasks"] != 22:
                raise ValueError("Missing or changed quality smoke set")
            item = {
                "artifact_sha256": entry.sha256,
                "artifact_bytes": Path(entry.path).stat().st_size,
                "precision": entry.precision,
                "workloads": workload_report,
                "smoke_quality": {
                    "passed": quality["passed"],
                    "tasks": 22,
                    "categories": {},
                },
                "manifest_sha256": file_hash(output / "manifest.json"),
                "requests_sha256": file_hash(output / "requests.jsonl"),
            }
            for outcome in quality["outcomes"]:
                category = outcome["category"]
                bucket = item["smoke_quality"]["categories"].setdefault(
                    category, {"passed": 0, "tasks": 0}
                )
                bucket["tasks"] += 1
                bucket["passed"] += int(outcome["passed"])
            session["models"][model] = item
        if all_inputs is None:
            all_inputs = reference_inputs
        elif all_inputs != reference_inputs:
            raise ValueError("Workload prompts differ between benchmark blocks")
        reports.append(session)

    batch_path = ROOT / "benchmarks/results/benchmark-followup-batching-20261120"
    batch = json.loads((batch_path / "summary.json").read_text())
    batch_manifest = json.loads((batch_path / "manifest.json").read_text())
    if batch_manifest["trials"] != 10 or batch["quality"]["greedy_mismatches"]:
        raise ValueError("Batching validation failed")
    if any(len(rows) != 22 for rows in batch["quality"]["outcomes"].values()):
        raise ValueError("Batching quality set changed")
    batch_report = {
        "manifest_sha256": file_hash(batch_path / "manifest.json"),
        "summary_sha256": file_hash(batch_path / "summary.json"),
        "pairs_sha256": file_hash(batch_path / "pairs.jsonl"),
        "outcomes_sha256": file_hash(batch_path / "requests.jsonl"),
        "trials": batch_manifest["trials"],
        "greedy_mismatches": batch["quality"]["greedy_mismatches"],
        "quality_passed": {
            arm: sum(row["passed"] for row in outcomes)
            for arm, outcomes in batch["quality"]["outcomes"].items()
        },
        "arms": {},
    }
    for arm, values in batch["arms"].items():
        batch_report["arms"][arm] = {
            "short_p50_ms": values["short_latency_ms"]["p50"],
            "short_ttft_p50_ms": values["short_ttft_ms"]["p50"],
            "short_queue_p50_ms": values["short_queue_ms"]["p50"],
            "long_p50_ms": values["long_latency_ms"]["p50"],
            "makespan_p50_ms": values["makespan_ms"]["p50"],
            "short_before_long": values["short_finished_before_long"],
            "aggregate_tokens_per_second": values[
                "aggregate_generated_tokens_per_second"
            ],
            "median_worker_rss_bytes": values["worker_rss_bytes"]["median"],
            "swap_trials": values["worker_swap_observed_trials"],
        }
    result = {
        "sessions": reports,
        "two_slot_batching": batch_report,
        "scope": "Three precision configs in two sequential blocks; same-source Qwen2.5 0.5B weights, tokenizer, backend, workloads and sampling. Q4 block 1 is contaminated and excluded. Q8/F16 have two valid blocks; Q4 has one. Ten trials and two warmups per workload/block. No CPU isolation, energy data, or significance claim.",
        "concurrency": "Concurrent/mixed workload cases queued on one native slot; not native multi-slot batching measurements.",
        "excluded": {
            "block_1_q4": "A second benchmark launch overlapped briefly with the final quality phase. Preserve its raw data, but exclude all Q4 results from block 1."
        },
        "quality": "Twenty-two original self-authored strict smoke cases per model/block; instrumentation check only, not representative quality evidence.",
        "limits": [
            "n=10 is exploratory; p95 is unstable and p99 is unavailable.",
            "Four-vCPU shared VM; workload order and contention affect measurements.",
            "RSS is sampled worker peak, not total host memory.",
            "Output token counts can differ with EOS; throughput uses observed generated tokens.",
            "Memory-limit failures remain in the results.",
            "No GPU, Apple Silicon, energy, or power data.",
        ],
    }
    (
        ROOT / "benchmarks/results/benchmark-followup-20261120/validated-summary.json"
    ).write_text(json.dumps(result, indent=2) + "\n")
    lines = [
        "# Fresh CPU precision benchmark",
        "",
        "Two sequential benchmark blocks compare the frozen Qwen2.5 0.5B F16, Q8_0 and Q4_K_M artifacts from the same source checkpoint on the pinned llama.cpp CPU backend. Each block has ten measured trials and two warmups per workload. Prompt inputs, output caps, context, thread count, sampler settings and runtime code are controlled; precision is the treatment factor. This is a single shared VM study with small samples, not a production SLA or formal significance test. A brief accidental overlap occurred during the final Q4 quality phase of block 1; all Q4 block-1 latency, throughput, memory and quality values are explicitly excluded. The raw observations and interruption record are retained.",
        "",
        "Each table cell reports block 1 / block 2. Latency is median total request time in milliseconds; throughput is aggregate observed generated tokens per second over the block makespan.",
        "",
        "| Model | Workload | P50 latency ms, block 1 / 2 | P95 latency ms, block 1 / 2 | Tokens/s, block 1 / 2 | Completed / attempted per block |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        for workload in reports[0]["models"][model]["workloads"]:
            first = reports[0]["models"][model]["workloads"][workload]
            second = reports[1]["models"][model]["workloads"][workload]
            first_valid = not (model.endswith("q4_k_m"))
            if first_valid:
                first_p50 = f"{first['p50_latency_ms']:.1f}"
                first_p95 = f"{first['p95_latency_ms']:.1f}"
                first_rate = f"{first['aggregate_tokens_per_second']:.2f}"
                first_complete = f"{first['completed']}/{first['attempted']}"
            else:
                first_p50 = first_p95 = first_rate = first_complete = "excluded"
            lines.append(
                f"| {model} | {workload} | {first_p50} / {second['p50_latency_ms']:.1f} | {first_p95} / {second['p95_latency_ms']:.1f} | {first_rate} / {second['aggregate_tokens_per_second']:.2f} | {first_complete} / {second['completed']}/{second['attempted']} |"
            )
    lines += [
        "",
        "The memory-constrained workload preserves admission failures rather than treating them as zero latency. Worker RSS is sampled process memory, not total physical memory. Workloads named concurrent and mixed used one native slot and therefore measure queued single-slot behavior, not continuous batching.",
        "",
        "## Storage and smoke quality",
        "",
        "| Precision | Artifact bytes | Strict smoke block 1 | Strict smoke block 2 |",
        "|---|---:|---:|---:|",
    ]
    for model in MODELS:
        rows = [session["models"][model] for session in reports]
        first_quality = (
            "excluded"
            if model.endswith("q4_k_m")
            else f"{rows[0]['smoke_quality']['passed']}/22"
        )
        lines.append(
            f"| {model} | {rows[0]['artifact_bytes']:,} | {first_quality} | {rows[1]['smoke_quality']['passed']}/22 |"
        )
    lines += [
        "",
        "Smoke scoring is strict output-format scoring on the original 22 self-authored cases; it is not held-out quality evidence. The frozen 600-case-per-precision study remains separate and controls substitution decisions.",
        "",
        "## Artifact size and sampled worker RSS",
        "",
        "Artifact size is exact file storage. Sampled worker RSS is the median 10 ms sampler peak, not total host memory.",
        "",
        "| Model | Artifact bytes | File-size change vs FP16 | Short-workload RSS MiB, block 1 / 2 | Memory-constrained RSS MiB, block 1 / 2 |",
        "|---|---:|---:|---:|---:|",
    ]
    baseline_size = reports[0]["models"]["qwen2.5-0.5b-instruct-f16"]["artifact_bytes"]
    for model in MODELS:
        first = reports[0]["models"][model]
        second = reports[1]["models"][model]
        delta = (first["artifact_bytes"] / baseline_size - 1) * 100
        change = f"{delta:+.1f}%"
        if model.endswith("q4_k_m"):
            short_rss = (
                "excluded / "
                + f"{second['workloads']['short']['median_sampled_peak_worker_rss_bytes'] / 1024**2:.0f}"
            )
            memory_rss = (
                "excluded / "
                + f"{second['workloads']['memory_constrained']['median_sampled_peak_worker_rss_bytes'] / 1024**2:.0f}"
            )
        else:
            short_rss = f"{first['workloads']['short']['median_sampled_peak_worker_rss_bytes'] / 1024**2:.0f} / {second['workloads']['short']['median_sampled_peak_worker_rss_bytes'] / 1024**2:.0f}"
            memory_rss = f"{first['workloads']['memory_constrained']['median_sampled_peak_worker_rss_bytes'] / 1024**2:.0f} / {second['workloads']['memory_constrained']['median_sampled_peak_worker_rss_bytes'] / 1024**2:.0f}"
        lines.append(
            f"| {model} | {first['artifact_bytes']:,} | {change} | {short_rss} | {memory_rss} |"
        )
    lines += [
        "",
        "File size reduction is not a claim of total-memory savings. RSS includes runtime libraries, mappings and context allocations; this VM has no isolated hardware memory counter.",
        "",
        "## Reproduction and raw records",
        "",
        "Workload file: ../workloads/cpu-v2-followup.json. Exact model, backend, code, platform and workload hashes are retained per run. Raw JSONL preserves every measured request, token IDs, outputs, queue timing, observed prompt/output lengths, sampled RSS and failures. Both precision blocks, the interrupted overlap attempt, and the paired batching run are retained under benchmark-followup-20261120, benchmark-followup-20261120-session2, benchmark-followup-20261120-session2-interrupted, and benchmark-followup-batching-20261120. The erroneous overlap and its exclusion are explicitly recorded.",
        "",
        "Run lattice benchmark --model MODEL --workload-file benchmarks/workloads/cpu-v2-followup.json --trials 10 --warmups 2 --quality --output NEW_DIRECTORY for another block. Use a fresh directory.",
        "",
        "## Paired one-slot versus two-slot serving",
        "",
        "This separate test used the same FP16 model and paired short/long requests. The short request arrived 20 ms after the long request's first text chunk. Ten trials per arm were run with both workers resident, alternating arm order. Greedy token IDs matched for every request.",
        "",
        "| Native slots | Short-request P50 ms | Short TTFT P50 ms | Short queue P50 ms | Long-request P50 ms | Pair makespan P50 ms | Short finished before long | Tokens/s | Median sampled worker RSS |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| 1 | {batch_report['arms']['slots-1']['short_p50_ms']:.1f} | {batch_report['arms']['slots-1']['short_ttft_p50_ms']:.1f} | {batch_report['arms']['slots-1']['short_queue_p50_ms']:.3f} | {batch_report['arms']['slots-1']['long_p50_ms']:.1f} | {batch_report['arms']['slots-1']['makespan_p50_ms']:.1f} | {batch_report['arms']['slots-1']['short_before_long']}/10 | {batch_report['arms']['slots-1']['aggregate_tokens_per_second']:.2f} | {batch_report['arms']['slots-1']['median_worker_rss_bytes'] / 1024**2:.0f} MiB |",
        f"| 2 | {batch_report['arms']['slots-2']['short_p50_ms']:.1f} | {batch_report['arms']['slots-2']['short_ttft_p50_ms']:.1f} | {batch_report['arms']['slots-2']['short_queue_p50_ms']:.3f} | {batch_report['arms']['slots-2']['long_p50_ms']:.1f} | {batch_report['arms']['slots-2']['makespan_p50_ms']:.1f} | {batch_report['arms']['slots-2']['short_before_long']}/10 | {batch_report['arms']['slots-2']['aggregate_tokens_per_second']:.2f} | {batch_report['arms']['slots-2']['median_worker_rss_bytes'] / 1024**2:.0f} MiB |",
        "",
        f"In this workload, two slots reduced short-request P50 by {100 * (1 - batch_report['arms']['slots-2']['short_p50_ms'] / batch_report['arms']['slots-1']['short_p50_ms']):.1f}% and median queue wait from {batch_report['arms']['slots-1']['short_queue_p50_ms']:.3f} ms to {batch_report['arms']['slots-2']['short_queue_p50_ms']:.3f} ms. Long-request P50 changed by {100 * (batch_report['arms']['slots-2']['long_p50_ms'] / batch_report['arms']['slots-1']['long_p50_ms'] - 1):+.1f}%, pair makespan by {100 * (batch_report['arms']['slots-2']['makespan_p50_ms'] / batch_report['arms']['slots-1']['makespan_p50_ms'] - 1):+.1f}%, and aggregate throughput by {100 * (batch_report['arms']['slots-2']['aggregate_tokens_per_second'] / batch_report['arms']['slots-1']['aggregate_tokens_per_second'] - 1):+.1f}%. This is a narrow 10-pair CPU result, not general production evidence. Both arms passed the same 11/22 strict smoke tasks, with no greedy mismatches or sampled worker swap.",
        "",
        "## Quality context",
        "",
        "The full frozen task evaluation and WikiText corpus benchmark are in [dataset_results.md](dataset_results.md): 1,728 scored model-case outputs and 72 explicit context skips; full-corpus PPL 17.4152 FP16, 17.5250 Q8_0 (+0.63%), and 18.0919 Q4_K_M (+3.89%). Q4 exceeds the existing proposed 2% PPL tolerance. Q8 remains unqualified for automatic substitution. These fresh performance observations do not relax those quality gates.",
        "",
        "No automatic model or precision policy is qualified by this run.",
        "",
    ]
    (ROOT / "docs/benchmark_followup_results.md").write_text("\n".join(lines))
    print("Wrote validated benchmark summary and report")


if __name__ == "__main__":
    main()

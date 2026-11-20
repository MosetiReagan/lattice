"""Enforce frozen latency/throughput/quality gates on paired held-out traces."""

import json
import random
from pathlib import Path

from lattice.config import file_hash

ROOT = Path(__file__).resolve().parents[1]


def percentile(values, probability):
    if not values:
        raise ValueError("Cannot calculate an empty distribution")
    ordered = sorted(values)
    index = probability * (len(ordered) - 1)
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def trace_measurement(result):
    rows = result["rows"]
    completed = [row for row in rows if row["status"] == "completed"]
    return {
        "interactive_ms": [
            row["latency_ms"] for row in completed if row["class"] == "interactive"
        ],
        "bulk_ms": [row["latency_ms"] for row in completed if row["class"] == "bulk"],
        "tokens": sum(row["completion_tokens"] for row in completed),
        "seconds": result["makespan_seconds"],
        "errors": len(rows) - len(completed),
        "worker_rss_bytes": result["worker_rss_peak_bytes"],
        "control_rss_bytes": result["control_plane_rss_peak_bytes"],
        "swap_bytes": result["worker_swap_peak_bytes"],
        "dispatch_lateness_ms": [row["dispatch_lateness_ms"] for row in completed],
    }


def metrics(pairs, baseline):
    native = [pair[baseline] for pair in pairs]
    candidate = [pair["candidate"] for pair in pairs]
    native_interactive = [v for trace in native for v in trace["interactive_ms"]]
    candidate_interactive = [v for trace in candidate for v in trace["interactive_ms"]]
    native_p95 = percentile(native_interactive, 0.95)
    candidate_p95 = percentile(candidate_interactive, 0.95)
    native_tps = sum(trace["tokens"] for trace in native) / sum(
        trace["seconds"] for trace in native
    )
    candidate_tps = sum(trace["tokens"] for trace in candidate) / sum(
        trace["seconds"] for trace in candidate
    )
    return {
        "baseline_p95_ms": native_p95,
        "candidate_p95_ms": candidate_p95,
        "p95_ratio": candidate_p95 / native_p95,
        "baseline_tokens_per_second": native_tps,
        "candidate_tokens_per_second": candidate_tps,
        "throughput_ratio": candidate_tps / native_tps,
        "baseline_bulk_p95_ms": percentile(
            [v for trace in native for v in trace["bulk_ms"]], 0.95
        ),
        "candidate_bulk_p95_ms": percentile(
            [v for trace in candidate for v in trace["bulk_ms"]], 0.95
        ),
        "baseline_errors": sum(trace["errors"] for trace in native),
        "candidate_errors": sum(trace["errors"] for trace in candidate),
    }


def bootstrap(sessions, baseline, replicates=10000):
    rng = random.Random(780912)
    latency = []
    throughput = []
    for _ in range(replicates):
        sampled = []
        for _ in sessions:
            session = sessions[rng.randrange(len(sessions))]
            sampled.extend(session[rng.randrange(len(session))] for _ in session)
        values = metrics(sampled, baseline)
        latency.append(values["p95_ratio"])
        throughput.append(values["throughput_ratio"])
    return {
        "replicates": replicates,
        "seed": 780912,
        "p95_ratio_95_interval": [
            percentile(latency, 0.025),
            percentile(latency, 0.975),
        ],
        "throughput_ratio_95_interval": [
            percentile(throughput, 0.025),
            percentile(throughput, 0.975),
        ],
        "method": "Percentile hierarchical paired bootstrap: resample sessions then whole paired traces within sessions; statistics recomputed on sampled trace requests.",
    }


def main():
    protocol_path = ROOT / "benchmarks/workloads/burst-coalescing-confirmation-v1.json"
    protocol = json.loads(protocol_path.read_text())
    folder = ROOT / "benchmarks/results/burst-coalescing-confirmation-v1"
    orchestration = json.loads((folder / "orchestration.json").read_text())
    if orchestration["status"] != "completed":
        raise ValueError(
            "Require all frozen sessions; no optional stopping or partial win"
        )
    if file_hash(protocol_path) != orchestration["protocol_sha256"]:
        raise ValueError("Protocol changed during confirmation")
    candidate = protocol["candidate"]
    baselines = protocol["baselines"]
    sessions = []
    provenance = []
    mismatches = []
    errors = []
    request_counts = {}
    sources = set()
    runners = set()
    identities = set()
    task_correctness = {}
    workload_hashes = []
    for session_index, session_spec in enumerate(protocol["sessions"], start=1):
        current = folder / f"session-{session_index}"
        manifest_path = current / "manifest.json"
        results_path = current / "results.jsonl"
        manifest = json.loads(manifest_path.read_text())
        if (
            manifest["seed"] != session_spec["seed"]
            or manifest["trace_count"] != session_spec["traces"]
        ):
            raise ValueError("Session deviates from frozen seed or trace count")
        if set(manifest["arms"]) != set(baselines + [candidate]):
            raise ValueError("Baseline or candidate changed")
        sources.add(manifest["source"]["sha256"])
        runners.add(manifest["runner_sha256"])
        identities.add((manifest["backend_sha256"], manifest["model_sha256"]))
        if (
            manifest["worker_address_space_mb"] != 4096
            or manifest["context_per_request"] != 2048
            or manifest["threads"] != 4
        ):
            raise ValueError("Frozen memory/context/thread configuration changed")
        workload_hashes.append(file_hash(manifest_path))
        results = [json.loads(line) for line in results_path.read_text().splitlines()]
        if len(results) != session_spec["traces"] * len(manifest["arms"]):
            raise ValueError("Incomplete arm/trace matrix")
        lookup = {(r["trace"], r["arm"]): r for r in results}
        if len(lookup) != len(results):
            raise ValueError("Duplicate arm/trace")
        paired = []
        for trace_index, requests in enumerate(manifest["traces"]):
            expected = {request["id"]: request for request in requests}
            maps = {}
            for arm in manifest["arms"]:
                result = lookup[trace_index, arm]
                records = {row["id"]: row for row in result["rows"]}
                if records.keys() != expected.keys() or len(result["rows"]) != len(
                    expected
                ):
                    raise ValueError("Changed or incomplete request trace")
                if result["batch_tokens"] != 256 or result["ubatch_tokens"] != 256:
                    raise ValueError("Unexpected batch tuning")
                expected_slots = 8 if arm == "native8" else 4
                if result["native_slots"] != expected_slots:
                    raise ValueError("Slot configuration differs")
                for key, row in records.items():
                    if row["status"] != "completed":
                        errors.append(
                            {
                                "session": session_index,
                                "trace": trace_index,
                                "arm": arm,
                                "id": key,
                                "status": row["status"],
                            }
                        )
                        continue
                    request = expected[key]
                    if (
                        row["prompt_sha256"] != request["prompt_sha256"]
                        or row["arrival_seconds"] != request["arrival_seconds"]
                    ):
                        raise ValueError("Prompt or exogenous arrival changed")
                    if (
                        row["completion_tokens"] > request["max_tokens"]
                        or row["prompt_tokens"] + request["max_tokens"]
                        > manifest["context_per_request"]
                    ):
                        raise ValueError("Output/context limit violated")
                    if row["completion_tokens"] != len(row["token_ids"]):
                        raise ValueError(
                            "Throughput counter differs from actual emitted token IDs"
                        )
                    request_counts[arm] = request_counts.get(arm, 0) + 1
                    counts = task_correctness.setdefault(
                        arm, {"completed": 0, "exact_correct": 0}
                    )
                    counts["completed"] += 1
                    counts["exact_correct"] += int(row["exact_correct"])
                maps[arm] = records
            for key in expected:
                reference = maps["native8"][key]
                if reference["status"] != "completed":
                    continue
                for arm in [candidate, "simple_cost4"]:
                    row = maps[arm][key]
                    if row["status"] == "completed" and (
                        row["token_ids"] != reference["token_ids"]
                        or row["text"] != reference["text"]
                        or row["prompt_tokens"] != reference["prompt_tokens"]
                    ):
                        mismatches.append(
                            {
                                "session": session_index,
                                "trace": trace_index,
                                "arm": arm,
                                "id": key,
                            }
                        )
            paired.append(
                {
                    **{
                        arm: trace_measurement(lookup[trace_index, arm])
                        for arm in baselines
                    },
                    "candidate": trace_measurement(lookup[trace_index, candidate]),
                }
            )
        sessions.append(paired)
        provenance.append(
            {
                "manifest_path": str(manifest_path.relative_to(ROOT)),
                "manifest_sha256": file_hash(manifest_path),
                "results_sha256": file_hash(results_path),
                "seed": session_spec["seed"],
            }
        )
    if len(sources) != 1:
        raise ValueError("Runtime source changed between sessions")
    if len(runners) != 1 or len(identities) != 1:
        raise ValueError("Runner, model or backend changed between sessions")
    all_pairs = [pair for session in sessions for pair in session]
    comparisons = {}
    for baseline in baselines:
        values = metrics(all_pairs, baseline)
        per_session = [metrics(session, baseline) for session in sessions]
        uncertainty = bootstrap(sessions, baseline)
        comparisons[baseline] = {
            "point_estimates": values,
            "per_session": per_session,
            "uncertainty": uncertainty,
        }
    primary = comparisons["native8"]
    latency_pass = primary["uncertainty"]["p95_ratio_95_interval"][1] <= 0.8 and all(
        session["p95_ratio"] <= 0.8 for session in primary["per_session"]
    )
    throughput_pass = primary["uncertainty"]["throughput_ratio_95_interval"][
        0
    ] >= 0.95 and all(
        session["throughput_ratio"] >= 0.95 for session in primary["per_session"]
    )
    quality_pass = not mismatches and not errors
    worker_cap = 4096 * 1024**2
    resource_pass = all(
        pair[arm]["worker_rss_bytes"] is not None
        and pair[arm]["worker_rss_bytes"] <= worker_cap
        and not pair[arm]["swap_bytes"]
        for pair in all_pairs
        for arm in baselines + ["candidate"]
    )
    gates = {
        "latency": latency_pass,
        "throughput": throughput_pass,
        "quality_and_errors": quality_pass,
        "worker_cap_and_no_swap": resource_pass,
    }
    resource_summary = {}
    for arm in baselines + ["candidate"]:
        items = [pair[arm] for pair in all_pairs]
        resource_summary[arm] = {
            "max_worker_rss_bytes": max(x["worker_rss_bytes"] for x in items),
            "max_control_plane_rss_bytes": max(x["control_rss_bytes"] for x in items),
            "max_dispatch_lateness_ms": max(
                v for x in items for v in x["dispatch_lateness_ms"]
            ),
        }
    report = {
        "protocol_sha256": file_hash(protocol_path),
        "analysis_sha256": file_hash(Path(__file__)),
        "sessions": provenance,
        "source_sha256": next(iter(sources)),
        "runner_sha256": next(iter(runners)),
        "backend_model_sha256": list(next(iter(identities))),
        "paired_traces": len(all_pairs),
        "completed_request_counts": request_counts,
        "task_correctness": task_correctness,
        "mismatches": mismatches,
        "errors": errors,
        "comparisons": comparisons,
        "resources": resource_summary,
        "gates": gates,
        "restricted_gate_pass": all(gates.values()),
        "scope": "Only the frozen synthetic long-input/short-input CPU burst and finite native tuning sweep. Not broad engine/model/production superiority. A conventional bounded admission heuristic, not a novel attention/kernel algorithm. Default serving configuration unchanged.",
    }
    (folder / "analysis.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = [
        "# Held-out burst admission confirmation",
        "",
        "This experiment tests opt-in four-slot Lattice admission with a 50 ms grace for default-priority requests exceeding 1,024 input bytes or 32 output tokens. Higher-priority requests bypass the grace. Latency includes grace, queueing and generation. The default priority/FIFO serving policy is unchanged.",
        "",
        "Development compared native 1/2/3/4/8 slots and native8 batch sizes 64/128/256/512/1024. Native8 with batch256 was frozen as the strongest interactive-P95 native development baseline. A thin four-slot cost-priority baseline outside Lattice is also reported. This is a finite tuning sweep, not a globally optimal competitor claim.",
        "",
        "## Frozen confirmation",
        "",
        "Three sessions each contain ten untouched trace seeds. Each trace has six diverse long-input copy tasks followed by six short-input copy tasks at fixed, exogenous arrival times. Both arms use the same Qwen2.5 0.5B FP16 artifact, pinned native binary, four CPU threads, per-request 2k context and 4 GiB worker address-space limit. Actual EOS/output lengths are retained; no generation is forced to hit its cap.",
        "",
        "| Baseline | Interactive P95 ms | Candidate P95 ms | P95 ratio [95% interval] | Throughput baseline / candidate tokens/s | Throughput ratio [95% interval] |",
        "|---|---:|---:|---|---|---|",
    ]
    for baseline, result in comparisons.items():
        value = result["point_estimates"]
        interval = result["uncertainty"]
        lat = interval["p95_ratio_95_interval"]
        tps = interval["throughput_ratio_95_interval"]
        lines.append(
            f"| {baseline} | {value['baseline_p95_ms']:.1f} | {value['candidate_p95_ms']:.1f} | {value['p95_ratio']:.3f} [{lat[0]:.3f}, {lat[1]:.3f}] | {value['baseline_tokens_per_second']:.2f} / {value['candidate_tokens_per_second']:.2f} | {value['throughput_ratio']:.3f} [{tps[0]:.3f}, {tps[1]:.3f}] |"
        )
    lines += [
        "",
        "## Gate decision",
        "",
        f"Restricted gate pass: **{report['restricted_gate_pass']}**. Individual frozen gates: `{json.dumps(gates, sort_keys=True)}`.",
        "",
        f"Raw results contain {len(mismatches)} token/text/prompt-length mismatches and {len(errors)} failed requests across {len(all_pairs)} paired traces. Exact-match equality establishes only this finite tested scope. Numerical task correctness is separate from baseline-output preservation.",
        "",
        "Absolute copy-task exact correctness (stripped output must equal the requested value): "
        + "; ".join(
            f"{arm}: {counts['exact_correct']}/{counts['completed']}"
            for arm, counts in task_correctness.items()
        )
        + ". Identical incorrect answers are not evidence of good task quality.",
        "",
        "The latency target requires at least 20% interactive P95 improvement and the throughput target permits at most 5% loss. Both must hold in every session and for the predeclared clustered confidence bounds. If a gate fails or remains inconclusive, these measurements do not qualify the claim. Gates were not relaxed.",
        "",
        "| Session | Native interactive P95 ms | Candidate P95 ms | P95 ratio | Throughput ratio | Native / candidate bulk P95 ms |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for i, value in enumerate(primary["per_session"], start=1):
        lines.append(
            f"| {i} | {value['baseline_p95_ms']:.1f} | {value['candidate_p95_ms']:.1f} | {value['p95_ratio']:.3f} | {value['throughput_ratio']:.3f} | {value['baseline_bulk_p95_ms']:.1f} / {value['candidate_bulk_p95_ms']:.1f} |"
        )
    lines += [
        "",
        "## Resources and interpretation",
        "",
        "Worker and control-plane RSS are sampled separately; the worker hard limit is address space, not RSS. Control-plane RSS is the common benchmark harness process, not an isolated production gateway measurement. All raw dispatch lateness, EOS, request timings and failures are preserved in the result files. The confirmation contains only one burst family on one shared CPU VM; it does not certify GPU support, model-quality improvements, production prevalence or all workloads. Long-only and interactive-only traffic can respond differently to the opt-in delay. A separately configured admission shim can implement the same conventional heuristic; no exclusivity or new-kernel claim follows.",
        "",
        "The confidence intervals use 10,000 fixed-seed hierarchical paired bootstrap replicates, resampling sessions and whole traces. Three sessions on one VM are not independent hardware replications. The frozen protocol and source hashes are retained in the result directory. See [the competitive execution plan](competitive_execution_plan.md).",
        "",
    ]
    (ROOT / "docs/burst_admission_confirmation.md").write_text("\n".join(lines))
    print(
        json.dumps(
            {
                "gate_pass": report["restricted_gate_pass"],
                "gates": gates,
                "native_comparison": primary,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

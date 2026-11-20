"""Apply a separately frozen protocol to chat-framed confirmation data."""

import json
from pathlib import Path

from analyze_admission_confirmation import bootstrap, metrics, trace_measurement

from lattice.config import file_hash

ROOT = Path(__file__).resolve().parents[1]


def main():
    protocol_path = ROOT / "benchmarks/workloads/chat-burst-confirmation-v1.json"
    protocol = json.loads(protocol_path.read_text())
    root = ROOT / "benchmarks/results/chat-burst-confirmation-v1"
    state = json.loads((root / "orchestration.json").read_text())
    if state["status"] != "completed":
        raise ValueError("Require all predeclared sessions; no optional stopping")
    if state["protocol_sha256"] != file_hash(protocol_path):
        raise ValueError("Protocol changed during confirmation")
    candidate = protocol["candidate"]
    baselines = protocol["baselines"]
    primary_baseline = baselines[0]
    arms = baselines + [candidate]
    signatures = set()
    sessions = []
    provenance = []
    mismatches = []
    failures = []
    correctness = {arm: {"completed": 0, "exact_correct": 0} for arm in arms}
    host_cpu_records = []
    for index, spec in enumerate(protocol["sessions"], 1):
        folder = root / f"session-{index}"
        manifest_path = folder / "manifest.json"
        raw_path = folder / "results.jsonl"
        manifest = json.loads(manifest_path.read_text())
        if (
            manifest["seed"] != spec["seed"]
            or manifest["trace_count"] != spec["traces"]
            or manifest["arms"] != arms
        ):
            raise ValueError("Session differs from frozen selection")
        signatures.add(
            tuple(
                manifest[key]
                for key in (
                    "runner_sha256",
                    "transport_runner_sha256",
                    "model_sha256",
                    "backend_sha256",
                )
            )
            + (manifest["source"]["sha256"],)
        )
        if manifest["source"]["sha256"] != protocol["source_sha256"]:
            raise ValueError("Runtime source differs from frozen source")
        for key in ("threads", "context_per_request", "worker_address_space_mb"):
            if manifest[key] != protocol[key]:
                raise ValueError("Resource settings changed")
        for key in ("cpu_affinity", "settings_sha256"):
            if key in protocol and manifest.get(key) != protocol[key]:
                raise ValueError("CPU affinity or settings file changed")
        records = [json.loads(line) for line in raw_path.read_text().splitlines()]
        lookup = {(r["trace"], r["arm"]): r for r in records}
        if len(lookup) != len(records) or len(records) != spec["traces"] * len(arms):
            raise ValueError("Duplicate or incomplete trace/arm matrix")
        session = []
        for trace_index, trace in enumerate(manifest["traces"]):
            expected = {row["id"]: row for row in trace}
            maps = {}
            for arm in arms:
                result = lookup[trace_index, arm]
                host_cpu_records.append(
                    {
                        "session": index,
                        "trace": trace_index,
                        "arm": arm,
                        **result.get("host_cpu", {}),
                    }
                )
                settings = protocol["arm_settings"][arm]
                for key in ("native_slots", "batch_tokens", "ubatch_tokens"):
                    if result[key] != settings[key]:
                        raise ValueError("Frozen arm settings changed")
                rows = {row["id"]: row for row in result["rows"]}
                if rows.keys() != expected.keys() or len(rows) != len(result["rows"]):
                    raise ValueError("Incomplete/duplicate request IDs")
                for request_id, row in rows.items():
                    source = expected[request_id]
                    for key in ("prompt_sha256", "arrival_seconds", "max_tokens"):
                        if row[key] != source[key]:
                            raise ValueError("Source input or arrivals changed")
                    if row["status"] != "completed":
                        failures.append([index, trace_index, arm, request_id])
                        continue
                    if (
                        row["completion_tokens"] != len(row["token_ids"])
                        or row["completion_tokens"] > source["max_tokens"]
                        or row["prompt_tokens"] + source["max_tokens"]
                        > protocol["context_per_request"]
                    ):
                        raise ValueError(
                            "Token accounting or output/context cap violated"
                        )
                    correctness[arm]["completed"] += 1
                    correctness[arm]["exact_correct"] += int(row["exact_correct"])
                maps[arm] = rows
            for request_id in expected:
                reference = maps[primary_baseline][request_id]
                for arm in arms[1:]:
                    row = maps[arm][request_id]
                    if any(
                        row.get(key) != reference.get(key)
                        for key in (
                            "status",
                            "token_ids",
                            "text",
                            "prompt_tokens",
                            "exact_correct",
                        )
                    ):
                        mismatches.append([index, trace_index, arm, request_id])
            session.append(
                {
                    **{
                        arm: trace_measurement(lookup[trace_index, arm])
                        for arm in baselines
                    },
                    "candidate": trace_measurement(lookup[trace_index, candidate]),
                }
            )
        sessions.append(session)
        provenance.append(
            {
                "manifest_sha256": file_hash(manifest_path),
                "results_sha256": file_hash(raw_path),
                "seed": spec["seed"],
            }
        )
    if len(signatures) != 1:
        raise ValueError("Source, runner or model/backend identity changed")
    signature = next(iter(signatures))
    for key, value in zip(
        ("runner_sha256", "transport_runner_sha256", "model_sha256", "backend_sha256"),
        signature[:4],
        strict=True,
    ):
        if value != protocol[key]:
            raise ValueError("Model/backend/runner differs from protocol")
    paired = [trace for session in sessions for trace in session]
    comparisons = {
        baseline: {
            "point_estimates": metrics(paired, baseline),
            "per_session": [metrics(session, baseline) for session in sessions],
            "uncertainty": bootstrap(sessions, baseline),
        }
        for baseline in baselines
    }
    primary = comparisons[primary_baseline]
    latency_limit = protocol["latency_ratio_max"]
    throughput_limit = protocol["throughput_ratio_min"]
    gates = {
        "host_cpu_eligibility": all(
            record.get("available")
            and record["aggregate_steal_fraction"] <= protocol["host_cpu_steal_max"]
            and record["max_interval_steal_fraction"]
            <= protocol["host_cpu_interval_steal_max"]
            for record in host_cpu_records
        ),
        "latency": primary["uncertainty"]["p95_ratio_95_interval"][1] <= latency_limit
        and all(s["p95_ratio"] <= latency_limit for s in primary["per_session"]),
        "throughput": primary["uncertainty"]["throughput_ratio_95_interval"][0]
        >= throughput_limit
        and all(
            s["throughput_ratio"] >= throughput_limit for s in primary["per_session"]
        ),
        "quality_and_errors": not mismatches and not failures,
        "worker_cap_and_no_swap": all(
            trace[arm]["worker_rss_bytes"] is not None
            and trace[arm]["worker_rss_bytes"]
            <= protocol["worker_address_space_mb"] * 1024**2
            and not trace[arm]["swap_bytes"]
            for trace in paired
            for arm in baselines + ["candidate"]
        ),
    }
    report = {
        "protocol_sha256": file_hash(protocol_path),
        "analyzer_sha256": file_hash(Path(__file__)),
        "statistical_helpers_sha256": file_hash(
            ROOT / "scripts/analyze_admission_confirmation.py"
        ),
        "sessions": provenance,
        "identity_signature": signature,
        "paired_traces": len(paired),
        "host_cpu_records": host_cpu_records,
        "comparisons": comparisons,
        "task_correctness": correctness,
        "mismatches": mismatches,
        "failures": failures,
        "gates": gates,
        "restricted_gate_pass": all(gates.values()),
    }
    (root / "analysis.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = [
        "# Chat-framed burst confirmation",
        "",
        "This separately frozen study follows the failed raw-completion study; it does not overwrite or reclassify that failure. Each source instruction is rendered through the model's actual /apply-template endpoint before timing. Every arm receives identical rendered bytes, tokenizer, greedy sampler, output caps and exogenous arrivals. Template preparation and equal one-request warmup are excluded; reported latency includes admission grace, queueing and generation, not the full HTTP chat gateway.",
        "",
        f"Restricted gate pass: **{report['restricted_gate_pass']}**. Frozen gates: `{json.dumps(gates, sort_keys=True)}`.",
        "",
        "| Baseline | Interactive P95 ms | Candidate P95 ms | Ratio [95% interval] | Baseline / candidate tokens/s | Throughput ratio [95% interval] |",
        "|---|---:|---:|---|---|---|",
    ]
    for baseline, result in comparisons.items():
        point, ci = result["point_estimates"], result["uncertainty"]
        lat, tps = ci["p95_ratio_95_interval"], ci["throughput_ratio_95_interval"]
        lines.append(
            f"| {baseline} | {point['baseline_p95_ms']:.1f} | {point['candidate_p95_ms']:.1f} | {point['p95_ratio']:.3f} [{lat[0]:.3f}, {lat[1]:.3f}] | {point['baseline_tokens_per_second']:.3f} / {point['candidate_tokens_per_second']:.3f} | {point['throughput_ratio']:.3f} [{tps[0]:.3f}, {tps[1]:.3f}] |"
        )
    lines += [
        "",
        "| Session | Interactive P95 ratio | Throughput ratio | Baseline / candidate bulk P95 ms |",
        "|---|---:|---:|---|",
    ]
    for index, point in enumerate(primary["per_session"], 1):
        lines.append(
            f"| {index} | {point['p95_ratio']:.3f} | {point['throughput_ratio']:.3f} | {point['baseline_bulk_p95_ms']:.1f} / {point['candidate_bulk_p95_ms']:.1f} |"
        )
    lines += [
        "",
        f"There are {len(mismatches)} baseline-output/classification mismatches and {len(failures)} failed requests across {len(paired)} paired traces. Strict absolute copy-task correctness: "
        + "; ".join(
            f"{arm}: {c['exact_correct']}/{c['completed']}"
            for arm, c in correctness.items()
        )
        + ". No incorrect/EOS/cap-finished requests are excluded.",
        "",
        "Both performance conditions must hold in every session and for 10,000 fixed-seed hierarchical paired bootstrap confidence bounds. No additional confirmation traces or relaxed thresholds are allowed after seeing the result. Three sessions share one four-core CPU VM; they are not independent hardware replications. All source/model/backend/runner/protocol hashes and raw observations are retained.",
        "Every complete arm additionally records CPU steal. Aggregate steal must be <=5% and every sampled interval <=10%; unavailable/reset counters disqualify eligibility. A failed host gate invalidates qualification without dropping or selectively rerunning traces. These are prospective conditions; no earlier unmonitored result is retroactively labeled clean.",
        "",
        "This is a restricted synthetic burst-serving comparison for Qwen2.5 0.5B FP16, under the fixed worker cap and finite native tuning sweep. The timing pattern is deliberately a burst where short work follows expensive prefills. It establishes neither typical production prevalence nor general superiority over inference engines or peer-size model quality. Conventional admission delay/cost ordering can also be implemented outside Lattice; native execution kernels and batching belong to llama.cpp. Defaults remain unchanged, accelerator support is untested, and Lattice remains an unreleased development build.",
        "Chat framing aligns instruction requests with the model's intended interface; it is not a demonstrated fix for native batching-related numerical divergence. Any output-preservation pass applies only to the recorded finite prompts and configurations, not arbitrary future prompts.",
        "",
        "See [failed original confirmation](burst_admission_confirmation.md), [boundary regressions](admission_boundaries.md) and [competitive plan](competitive_execution_plan.md). Boundary results used the earlier raw framing and must not be described as chat-framed confirmation evidence.",
        "",
    ]
    (ROOT / "docs/chat_admission_confirmation.md").write_text("\n".join(lines))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

"""Select distinct native latency/throughput challengers on development only."""

import json
from pathlib import Path

from analyze_admission_confirmation import percentile

from lattice.config import file_hash

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / "benchmarks/results/chat-single-thread-tuning-v2"
    results = json.loads((folder / "summary.json").read_text())
    raw = [
        json.loads(line) for line in (folder / "results.jsonl").read_text().splitlines()
    ]
    if results != raw or len(results) != 11:
        raise ValueError("Require the complete predefined native tuning matrix")
    by_arm = {result["arm"]: result for result in results}
    summary = {}
    for arm, result in by_arm.items():
        completed = [row for row in result["rows"] if row["status"] == "completed"]
        summary[arm] = {
            "interactive_p95_ms": percentile(
                [
                    row["latency_ms"]
                    for row in completed
                    if row["class"] == "interactive"
                ],
                0.95,
            ),
            "bulk_p95_ms": percentile(
                [row["latency_ms"] for row in completed if row["class"] == "bulk"], 0.95
            ),
            "tokens_per_second": result["tokens_per_second"],
            "exact_correct": sum(row["exact_correct"] for row in completed),
            "errors": result["failures"],
            "host_cpu": result["host_cpu"],
        }
    native = [
        arm
        for arm in summary
        if arm.startswith("native") and not summary[arm]["errors"]
    ]
    latency_baseline = min(native, key=lambda arm: summary[arm]["interactive_p95_ms"])
    throughput_baseline = max(native, key=lambda arm: summary[arm]["tokens_per_second"])
    baseline_arms = list(dict.fromkeys([latency_baseline, throughput_baseline]))
    if len(baseline_arms) == 1:
        baseline_arms.append("simple_cost2")
    reference = {row["id"]: row for row in by_arm[latency_baseline]["rows"]}
    for arm, result in by_arm.items():
        summary[arm]["output_mismatches"] = sum(
            any(
                row.get(key) != reference[row["id"]].get(key)
                for key in (
                    "status",
                    "prompt_sha256",
                    "prompt_tokens",
                    "text",
                    "token_ids",
                )
            )
            for row in result["rows"]
        )
    report = {
        "results_sha256": file_hash(folder / "results.jsonl"),
        "latency_baseline": latency_baseline,
        "throughput_baseline": throughput_baseline,
        "confirmation_baselines": baseline_arms,
        "candidate": "lattice_coalesce2",
        "arms": summary,
    }
    (folder / "analysis.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = [
        "# Pinned one-thread development",
        "",
        "This is a separate resource envelope: backend threads 1, all benchmark/control/native processes pinned to virtual CPU 0, same Qwen2.5 0.5B FP16 checkpoint, sampling, per-request context and worker cap. The failed raw study and unexecuted four-thread chat draft remain separate. No threshold is relaxed and no development observation is held-out evidence.",
        "",
        "The seed 9001 pinned pilot preserved outputs and strict task correctness 12/12, with candidate/native makespans 38.73/38.32 seconds. The complete seed 9002 tuning sweep below determines two native challengers: lowest interactive P95 and highest aggregate throughput. Distinct best configurations are both retained for confirmation; if they coincide, the thin cost-priority queue is the additional challenger. The thin queue is measured in development regardless.",
        "",
        "| Arm | Interactive P95 ms | Bulk P95 ms | Tokens/s | Strict task correct | Output mismatches | Errors | Mean / maximum interval CPU steal |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for arm, value in summary.items():
        host = value["host_cpu"]
        lines.append(
            f"| {arm} | {value['interactive_p95_ms']:.1f} | {value['bulk_p95_ms']:.1f} | {value['tokens_per_second']:.3f} | {value['exact_correct']}/12 | {value['output_mismatches']} | {value['errors']} | {host['aggregate_steal_fraction']:.3f} / {host['max_interval_steal_fraction']:.3f} |"
        )
    lines += [
        "",
        f"Prospective challengers selected only from this development sweep: `{baseline_arms}`. Candidate: `lattice_coalesce2`. All recorded results and host spikes remain visible. Development includes source-maintenance activity; no clean-host certification or win is claimed from it. During confirmation, no concurrent tests/builds/model jobs are allowed. Whole-arm mean steal <=5% and every sampled interval <=10% remain hard gates with no exclusions or selective retries.",
        "",
        "The tuning-v1 startup was interrupted after an accidental metadata edit. Its data/interruption marker are preserved; it was not used for selection. Tuning-v2 records the fixed runner, settings hash and affinity. This is provenance recovery, not a favorable-result replacement.",
        "",
        "The future confirmation budget is fixed at three sessions of ten paired traces, retaining the earlier study's sample size and performance/output thresholds. It is a new one-thread, chat-framed study, not a repair of the failed four-thread raw study. Every selected native baseline must independently satisfy the same latency and throughput conditions against the candidate. Results remain scoped to this synthetic burst; these conventional heuristics can also be implemented outside Lattice.",
        "",
    ]
    (ROOT / "docs/single_cpu_admission_development.md").write_text("\n".join(lines))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

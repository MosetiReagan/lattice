"""Validate and render the matched direct llama.cpp versus Lattice run."""

import json
import statistics
from pathlib import Path

from lattice.config import file_hash

ROOT = Path(__file__).resolve().parents[1]


def main():
    folders = [
        ROOT / "benchmarks/results/direct-lattice-headtohead-20261120",
        ROOT / "benchmarks/results/direct-lattice-headtohead-session2-20261120",
    ]
    sessions = []
    combined_rows = []
    combined_pairs = []
    for folder in folders:
        manifest = json.loads((folder / "manifest.json").read_text())
        summary = json.loads((folder / "summary.json").read_text())
        pairs = [
            json.loads(line)
            for line in (folder / "pairs.jsonl").read_text().splitlines()
        ]
        rows = [
            json.loads(line)
            for line in (folder / "requests.jsonl").read_text().splitlines()
        ]
        expected = len(manifest["workloads"]) * manifest["trials"]
        if len(pairs) != expected or len(rows) != expected * 2:
            raise ValueError("Incomplete direct/Lattice pair matrix")
        if (
            summary["pairs"] != expected
            or summary["greedy_mismatches"]
            or summary["text_mismatches"]
        ):
            raise ValueError("The two arms did not produce exactly matched output")
        keys = set()
        for pair in pairs:
            key = (pair["workload"], pair["trial"])
            if key in keys or set(pair["arms"]) != {"direct_llama_cpp", "lattice"}:
                raise ValueError("Duplicate or incomplete pair")
            keys.add(key)
            if (
                pair["arms"]["direct_llama_cpp"]["prompt_tokens"]
                != pair["arms"]["lattice"]["prompt_tokens"]
            ):
                raise ValueError("Prompt tokenization changed")
            expected_cap = manifest["worker_address_space_mb_by_workload"][
                pair["workload"]
            ]
            pair_rows = [
                r
                for r in rows
                if r["workload"] == pair["workload"] and r["trial"] == pair["trial"]
            ]
            if len(pair_rows) != 2 or {r["arm"] for r in pair_rows} != {
                "direct_llama_cpp",
                "lattice",
            }:
                raise ValueError("Missing or duplicate raw outcome")
            if {r["worker_address_space_mb"] for r in pair_rows} != {expected_cap}:
                raise ValueError("Worker memory caps differ")
            a, b = pair_rows
            if (
                a["token_ids"] != b["token_ids"]
                or a["text"] != b["text"]
                or a["prompt_sha256"] != b["prompt_sha256"]
                or a["prompt_tokens"] != b["prompt_tokens"]
            ):
                raise ValueError("Raw paired prompts or outputs differ")
        if not sessions:
            canonical = {(r["workload"], r["trial"]): r["prompt_sha256"] for r in pairs}
        elif canonical != {
            (r["workload"], r["trial"]): r["prompt_sha256"] for r in pairs
        }:
            raise ValueError("Different prompts between repeated sessions")
        sessions.append(
            {
                "manifest_sha256": file_hash(folder / "manifest.json"),
                "pairs_sha256": file_hash(folder / "pairs.jsonl"),
                "requests_sha256": file_hash(folder / "requests.jsonl"),
                "runner_sha256": manifest["runner_sha256"],
                "arm_order_seed": manifest.get("arm_order_seed"),
                "summary": summary,
            }
        )
        combined_rows.append(rows)
        combined_pairs.append(pairs)

    report = {
        "sessions": sessions,
        "workloads": {},
        "greedy_mismatches": sum(s["summary"]["greedy_mismatches"] for s in sessions),
        "text_mismatches": sum(s["summary"]["text_mismatches"] for s in sessions),
        "interpretation": "Both arms use the same pinned llama.cpp engine; this measures Lattice control-plane overhead, not superiority over another inference engine.",
        "limits": [
            "20 paired trials per workload across two sessions; still exploratory.",
            "Single shared CPU VM.",
            "No accelerators, energy, adaptive strategy, or multi-slot comparison.",
            "An earlier excluded exploratory run failed to apply the 2048 MiB workload override to either worker; both used 4096 MiB. The initial-cap-mismatch archive preserves it. Both reported sessions explicitly apply matched caps on every workload.",
        ],
    }
    lines = [
        "# Direct llama.cpp versus Lattice runtime",
        "",
        "This paired test uses the same pinned llama.cpp binary, libraries, FP16 Qwen2.5 0.5B artifact, one-slot worker settings, chat template, tokenizer, token-ID completion request and deterministic sampler on both arms. The direct arm sends requests to the native completion endpoint; the Lattice arm uses the Runtime request/admission/metrics path. It measures control-plane overhead, not superiority over another inference engine.",
        "",
        "The second session reran all five workloads with explicit per-workload matching of worker address-space caps and a different arm-order seed. An earlier exploratory run with an incorrect memory-cap protocol is preserved in the initial-cap-mismatch archive and excluded entirely; both reported sessions match caps on all five workloads. Across all included pairs, prompt and output token IDs match exactly.",
        "",
        "| Workload | Valid pairs | Direct P50 ms | Lattice P50 ms | Lattice P50 change | Direct / Lattice tokens/s |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for workload in [
        "short",
        "long_prompt",
        "long_response",
        "repeated_prefix",
        "memory_constrained",
    ]:
        direct_times = []
        lattice_times = []
        direct_tokens = lattice_tokens = 0
        direct_rss = []
        lattice_rss = []
        n = 0
        for rows, pairs in zip(combined_rows, combined_pairs, strict=True):
            for pair in pairs:
                if pair["workload"] != workload:
                    continue
                a = next(
                    r
                    for r in rows
                    if r["workload"] == workload
                    and r["trial"] == pair["trial"]
                    and r["arm"] == "direct_llama_cpp"
                )
                b = next(
                    r
                    for r in rows
                    if r["workload"] == workload
                    and r["trial"] == pair["trial"]
                    and r["arm"] == "lattice"
                )
                if pair["greedy_identical"] is not True:
                    raise ValueError("Greedy token mismatch")
                direct_times.append(a["elapsed_ms"])
                lattice_times.append(b["elapsed_ms"])
                direct_tokens += a["completion_tokens"]
                lattice_tokens += b["completion_tokens"]
                direct_rss.append(a["sampled_worker_rss_peak_bytes"])
                lattice_rss.append(b["sampled_worker_rss_peak_bytes"])
                n += 1
        direct_p50 = statistics.median(direct_times)
        lattice_p50 = statistics.median(lattice_times)
        delta = (lattice_p50 / direct_p50 - 1) * 100
        direct_tps = direct_tokens / (sum(direct_times) / 1000)
        lattice_tps = lattice_tokens / (sum(lattice_times) / 1000)
        report["workloads"][workload] = {
            "pairs": n,
            "direct_p50_ms": direct_p50,
            "lattice_p50_ms": lattice_p50,
            "lattice_p50_change_percent": delta,
            "direct_tokens_per_second": direct_tps,
            "lattice_tokens_per_second": lattice_tps,
            "direct_median_sampled_rss_bytes": sorted(direct_rss)[
                (len(direct_rss) - 1) // 2
            ],
            "lattice_median_sampled_rss_bytes": sorted(lattice_rss)[
                (len(lattice_rss) - 1) // 2
            ],
        }
        lines.append(
            f"| {workload} | {n} | {direct_p50:.1f} | {lattice_p50:.1f} | {delta:+.1f}% | {direct_tps:.2f} / {lattice_tps:.2f} |"
        )
    lines += [
        "",
        "Latency difference is (Lattice P50 / direct P50 - 1); positive means Lattice is slower. Throughput is observed generated tokens divided by summed per-request wall time, not system-wide sustainable throughput. Worker RSS is sampled process memory, not total host memory.",
        "",
        "These results do not support a claim that Lattice beats llama.cpp. They show near parity in direct single-slot execution on this tested model and CPU. The possible product advantage is the tested two-slot mixed-request path, which runs through the same upstream engine; that is useful product integration, not a new Lattice kernel.",
        "",
        "Both sessions' raw prompts, outputs, token IDs, caps, artifact hashes and manifests are retained under their result directories. The initial memory-cap mismatch archive is separate and excluded for that workload.",
        "",
    ]
    (
        ROOT
        / "benchmarks/results/direct-lattice-headtohead-20261120/validated-summary.json"
    ).write_text(json.dumps(report, indent=2) + "\n")
    (ROOT / "docs/direct_lattice_comparison.md").write_text("\n".join(lines))
    print(
        "Validated paired sessions:",
        sum(v["pairs"] for v in report["workloads"].values()),
    )


if __name__ == "__main__":
    main()

"""Validate repeated direct-native versus Lattice-runtime batching trials."""

import json
from pathlib import Path

from lattice.config import file_hash

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = [
    ROOT / "benchmarks/results/direct-lattice-batching-headtohead-20261120",
    ROOT / "benchmarks/results/direct-lattice-batching-headtohead-session2-20261120",
]


def main():
    sessions = []
    lines = [
        "# Direct llama.cpp versus Lattice two-slot serving",
        "",
        "Both arms run the same pinned two-slot llama.cpp worker, model, context, threads and server configuration. The direct arm submits concurrent completion streams directly to the native HTTP endpoint. The Lattice arm uses its request Runtime on the same backend path. The test isolates Lattice request/admission/streaming overhead; it is not a different-engine comparison.",
        "",
        "Each pair starts a 128-token-capped long generation, waits for its first nonempty text chunk, waits 20 ms, and submits an 8-token-capped short request. Both workers remain resident, but only one arm executes at a time. Trial arm order is seeded and randomized.",
        "",
        "| Block | Arm | Trials | Short P50 ms | Long P50 ms | Pair makespan P50 ms | Short finished before long | Greedy mismatches | Median sampled RSS MiB |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for folder in FOLDERS:
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
        if len(pairs) != manifest["trials"] or len(rows) != manifest["trials"] * 2:
            raise ValueError("Incomplete paired batching data")
        if summary["greedy_mismatches"]:
            raise ValueError("Greedy mismatch")
        for trial in range(manifest["trials"]):
            outcomes = [row for row in rows if row["trial"] == trial]
            if (
                len(outcomes) != 2
                or len({row["worker_address_space_mb"] for row in outcomes}) != 1
            ):
                raise ValueError("Trial not fully matched")
            direct = next(row for row in outcomes if row["arm"] == "direct_llama_cpp")
            lattice = next(row for row in outcomes if row["arm"] == "lattice_runtime")
            if (
                direct["long"]["token_ids"] != lattice["long"]["token_ids"]
                or direct["short"]["token_ids"] != lattice["short"]["token_ids"]
            ):
                raise ValueError("Greedy tokens changed")
        sessions.append(
            {
                "path": str(folder.relative_to(ROOT)),
                "manifest_sha256": file_hash(folder / "manifest.json"),
                "requests_sha256": file_hash(folder / "requests.jsonl"),
                "pairs_sha256": file_hash(folder / "pairs.jsonl"),
                "summary": summary,
            }
        )
        for arm in ("direct_llama_cpp", "lattice_runtime"):
            item = summary["arms"][arm]
            lines.append(
                f"| {folder.name} | {arm} | {manifest['trials']} | {item['short_p50_ms']['p50']:.1f} | {item['long_p50_ms']['p50']:.1f} | {item['makespan_ms']['p50']:.1f} | {item['short_finished_before_long']}/{manifest['trials']} | 0 | {item['rss_bytes']['median'] / 1024**2:.0f} |"
            )
    report = {
        "sessions": [
            {
                "path": item["path"],
                "manifest_sha256": item["manifest_sha256"],
                "requests_sha256": item["requests_sha256"],
                "pairs_sha256": item["pairs_sha256"],
                "greedy_mismatches": item["summary"]["greedy_mismatches"],
                "direct": {
                    k: v
                    for k, v in item["summary"]["arms"]["direct_llama_cpp"].items()
                    if k not in ("short_ttft_ms", "short_queue_ms")
                },
                "lattice": item["summary"]["arms"]["lattice_runtime"],
            }
            for item in sessions
        ],
        "interpretation": "The repeated 10-pair blocks estimate this narrow CPU arrival trace. Both paths use llama.cpp's native continuous batching; any measured difference is Lattice runtime/control-plane overhead, not a new batching algorithm.",
        "limits": [
            "Two blocks of ten pairs on one shared VM; still exploratory.",
            "Both arms ran sequentially while both workers were resident.",
            "Measured memory is sampled worker RSS; no energy or GPU measurements.",
            "This does not compare the Lattice product to another model-serving engine.",
        ],
    }
    output = (
        ROOT
        / "benchmarks/results/direct-lattice-batching-headtohead-20261120/validated-summary.json"
    )
    output.write_text(json.dumps(report, indent=2) + "\n")
    lines += [
        "",
        "Only measured total latency, makespan, output tokens and sampled RSS are compared here. Native queue time is unavailable. Historical direct summary TTFT/queue fields are invalid placeholders and must not be used; metric-errata.json preserves that correction. Real direct TTFT was captured only in the second block raw short.client_ttft_ms.",
        "",
        "This comparison cannot establish a unique Lattice batching advantage because both arms use the same upstream continuous-batching engine. The one-slot/two-slot product comparison against standard serial service is in [benchmark_followup_results.md](benchmark_followup_results.md).",
        "",
    ]
    (ROOT / "docs/direct_lattice_batching_comparison.md").write_text("\n".join(lines))
    print(
        f"Validated {sum(item['summary']['trials'] for item in sessions)} request pairs across two blocks"
    )


if __name__ == "__main__":
    main()

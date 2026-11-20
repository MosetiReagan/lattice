"""Validate three-arm exact-prompt cached output and report native-cache baseline."""

import json
from pathlib import Path

from lattice.config import file_hash

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / "benchmarks/results/adaptive-cache-vs-direct-20261120"
    manifest = json.loads((folder / "manifest.json").read_text())
    summary = json.loads((folder / "summary.json").read_text())
    rows = [
        json.loads(line)
        for line in (folder / "requests.jsonl").read_text().splitlines()
    ]
    if len(rows) != 3 * manifest["trials"] or summary["greedy_mismatches"]:
        raise ValueError("Incomplete or unequal cached comparison")
    for trial in range(manifest["trials"]):
        items = [row for row in rows if row["trial"] == trial]
        if len(items) != 3 or {row["arm"] for row in items} != set(manifest["arms"]):
            raise ValueError("Missing arm")
        for field in (
            "prompt_sha256",
            "prompt_tokens",
            "worker_address_space_mb",
            "model_sha256",
            "backend_sha256",
        ):
            if len({row[field] for row in items}) != 1:
                raise ValueError("Paired input/configuration mismatch: " + field)
        if (
            len({tuple(row["token_ids"]) for row in items}) != 1
            or len({row["text"] for row in items}) != 1
        ):
            raise ValueError("Paired output mismatch")
    report = {
        "manifest_sha256": file_hash(folder / "manifest.json"),
        "requests_sha256": file_hash(folder / "requests.jsonl"),
        "triples_verified": manifest["trials"],
        "greedy_mismatches": 0,
        "arms": summary["arms"],
        "limits": [
            "Only four exact public repeated-prefix prompt hashes, repeated across 30 trials.",
            "Direct cached and direct uncached arms share a worker and native cache state; result is a mixed cache-on/cache-off trace, not independent persistent cache pools.",
            "Model/engine/hardware are identical; no external engine or quality substitution comparison.",
        ],
    }
    (folder / "validated-summary.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = [
        "# Adaptive cache versus direct native cache",
        "",
        "Thirty three-arm trials compare direct uncached requests, direct llama.cpp native caching and Lattice adaptive execution on identical raw prompts. These are the exact public prompts covered by the existing measured policy; templates and tokenization are matched, and the adaptive arm selected cached execution on every measured request. Both workers have matching model/backend/context/thread/memory settings.",
        "",
        "| Arm | Requests | P50 ms | P95 ms | Median native cached tokens | Selected execution |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for arm, values in summary["arms"].items():
        lines.append(
            f"| {arm} | {values['elapsed_ms']['n']} | {values['elapsed_ms']['p50']:.1f} | {values['elapsed_ms']['p95']:.1f} | {values['tokens_cached']['p50']:.0f} | {json.dumps(values['strategies'], sort_keys=True)} |"
        )
    lines += [
        "",
        "All 30 triples matched exact greedy token IDs and text, with identical prompt-token lengths. Native caching and Lattice both reduce time versus uncached execution; the direct native-cache arm is the relevant baseline for unique value. This run does not demonstrate a 20% Lattice advantage over native caching.",
        "",
        "The direct cache-on and cache-off arms share native state; this is a mixed cache-on/cache-off trace. Only four exact prompt variants are repeated. Do not infer general held-out equivalence or broad cache performance. Earlier chat/raw framing mismatches are preserved in separate excluded pilot folders; their latency/output differences are not evidence of an optimization.",
        "",
        "Raw requests, token IDs, policy decisions, native timing/cached-token counters and hashes are retained alongside the validated summary. The broader decision and next gates are in [competitive_execution_plan.md](competitive_execution_plan.md).",
        "",
    ]
    (ROOT / "docs/adaptive_native_cache_comparison.md").write_text("\n".join(lines))
    print("Verified cached comparison:", manifest["trials"], "triples")


if __name__ == "__main__":
    main()

"""Report explicit different-model observations without optimization claims."""

import json
from pathlib import Path

from lattice.config import file_hash
from lattice.data.comparison import paired_comparison

ROOT = Path(__file__).resolve().parents[1]


def main():
    small_folder = ROOT / "benchmarks/results/dataset-quality-v1"
    large_folder = ROOT / "benchmarks/results/dataset-quality-1.5b-v1"
    corpus_folder = ROOT / "benchmarks/results/dataset-intake-1.5b-corpus-subset-v1"
    if not (large_folder / "completed.json").exists():
        raise SystemExit("Larger-model generation remains incomplete")
    small_id = "qwen2.5-0.5b-instruct-q8_0"
    large_id = "qwen2.5-1.5b-instruct-q8"
    small = json.loads((small_folder / "summary.json").read_text())[small_id]
    large = json.loads((large_folder / "summary.json").read_text())[large_id]
    corpus = json.loads((corpus_folder / "summary.json").read_text())
    sm = json.loads((small_folder / "manifest.json").read_text())
    lm = json.loads((large_folder / "manifest.json").read_text())
    if sm["frozen_subset_sha256"] != lm["frozen_subset_sha256"]:
        raise ValueError("Different frozen subsets")
    tokenizer_match = (
        sm["models"][small_id]["tokenizer_fingerprint"]
        == lm["models"][large_id]["tokenizer_fingerprint"]
    )
    paths = [small_folder / (small_id + ".jsonl"), large_folder / (large_id + ".jsonl")]
    rows = [
        {r["id"]: r for line in p.read_text().splitlines() if (r := json.loads(line))}
        for p in paths
    ]
    if rows[0].keys() != rows[1].keys():
        raise ValueError("Incomplete larger-model observation set")
    comparisons = {}
    for dataset in sorted(large):
        pairs = []
        excluded = []
        for key, a in rows[0].items():
            if a["dataset"] != dataset:
                continue
            b = rows[1][key]
            if any(
                a[f] != b[f]
                for f in [
                    "prompt_sha256",
                    "reference_sha256",
                    "max_tokens",
                    "prompt_tokens",
                ]
            ):
                raise ValueError("Inputs or token lengths differ")
            if a["status"] == b["status"] == "completed":
                pairs.append((a, b))
            else:
                excluded.append(
                    {
                        "id": key,
                        "small_status": a["status"],
                        "large_status": b["status"],
                    }
                )
        comparisons[dataset] = {
            "excluded": excluded,
            "answer": paired_comparison(
                [a["score"]["answer_correct"] for a, b in pairs],
                [b["score"]["answer_correct"] for a, b in pairs],
            )
            if pairs
            else None,
        }
    report = {
        "baseline": small_id,
        "candidate": large_id,
        "tokenizer_metadata_match": tokenizer_match,
        "paired": comparisons,
        "source_files": [
            {"path": str(p.relative_to(ROOT)), "sha256": file_hash(p)} for p in paths
        ],
        "scope": "Different checkpoint/parameter count, not a same-source optimization; no cost/latency or validated routing claim",
        "reporter_sha256": file_hash(Path(__file__)),
    }
    (large_folder / "different-model-comparison.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    lines = [
        "# Separate 1.5B model dataset observations",
        "",
        "This study adds real responses from the existing explicit `qwen2.5-1.5b-instruct-q8` model to the same 600 frozen evaluation cases used by the 0.5B precision study. **Different weights and parameter count: this is not a same-checkpoint optimization comparison, validated model routing or a latency/cost improvement claim.** The original task count does not increase.",
        "",
        "Model/source/binary hashes, fixed caps/sampling, actual token counts, outputs and licensing remain in [the separate quality folder](../benchmarks/results/dataset-quality-1.5b-v1/manifest.json). Tokenizer metadata match across these Qwen checkpoints: **"
        + str(tokenizer_match).lower()
        + "**. Every paired input prompt/reference/cap/token count was checked.",
        "",
        "| Configuration | 0.5B Q8 answer / scored; strict / scored | 1.5B Q8 answer / scored; strict / scored | 1.5B exclusions |",
        "|---|---:|---:|---:|",
    ]
    for dataset in sorted(large):
        a, b = small[dataset], large[dataset]
        lines.append(
            f"| {dataset} | {a['answer_correct']}/{a['scored']}; {a['strict_correct']}/{a['scored']} | {b['answer_correct']}/{b['scored']}; {b['strict_correct']}/{b['scored']} | {b['excluded']} |"
        )
    lines += [
        "",
        "Accuracy uses the same documented Lattice generated-answer/canonical-rubric protocols, not official leaderboard scores. Long inputs are skipped explicitly, never truncated; length-limited outputs remain scored. Per-task intervals, strata and output-cap finishes are in [summaries](../benchmarks/results/dataset-quality-1.5b-v1/summary.json). Conservative paired differences and exclusions are in [different-model-comparison.json](../benchmarks/results/dataset-quality-1.5b-v1/different-model-comparison.json). Public benchmark contamination, related-source correlation and small balanced samples limit generalization. No automatic model-substitution policy is qualified.",
        "",
        "## Additional corpus observation",
        "",
    ]
    item = corpus["models"][large_id]
    lines += [
        f"The separate 1.5B model measured **PPL {item['perplexity']:.4f}** (cross-entropy {item['cross_entropy_nats']:.6f} nats) on a **predeclared first-{item['evaluated_chunks']}-chunk subset**, context 256, scoring the native final half of each chunk: nominally {item['nominal_scored_tokens']:,} tokens. Cross-entropy is derived as ln of the rounded reported PPL. This is a subset, unlike the primary 0.5B study’s 1,167 chunks. Do not compare these PPL point estimates as if their evaluation scopes were identical.",
        "",
        "[Native command, hashes, uncertainty and subset declaration](../benchmarks/results/dataset-intake-1.5b-corpus-subset-v1/summary.json) are preserved. Operational wall times are not controlled latency/throughput measurements; no quality-cost routing conclusion follows from this observation alone.",
        "",
        "See [data methodology and errata](datasets.md) and [the primary precision study](dataset_results.md).",
        "",
    ]
    (ROOT / "docs/larger_model_dataset_results.md").write_text("\n".join(lines))
    print("Saved separate different-model quality/corpus observations")


if __name__ == "__main__":
    main()

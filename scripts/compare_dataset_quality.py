"""Retain paired quality changes and exclusions; never auto-promote a policy."""

import argparse
import json
from pathlib import Path

from lattice.config import file_hash
from lattice.data.comparison import paired_comparison

ROOT = Path(__file__).resolve().parents[1]
MODELS = [
    "qwen2.5-0.5b-instruct-f16",
    "qwen2.5-0.5b-instruct-q8_0",
    "qwen2.5-0.5b-instruct-q4_k_m",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results", type=Path, default=ROOT / "benchmarks/results/dataset-quality-v1"
    )
    args = parser.parse_args()
    if not (args.results / "completed.json").exists():
        raise SystemExit(
            "Require completed frozen-subset runs; preserve partial outcomes separately"
        )
    models = {}
    for model in MODELS:
        rows = [
            json.loads(line)
            for line in (args.results / (model + ".jsonl")).read_text().splitlines()
        ]
        if len({r["id"] for r in rows}) != len(rows):
            raise ValueError("Duplicate model outcome ID")
        models[model] = {r["id"]: r for r in rows}
    baseline = models[MODELS[0]]
    report = {
        "baseline": MODELS[0],
        "scope": "Frozen stratified generated-answer sample; no official leaderboard or foundation-model holdout claim",
        "comparison_script_sha256": file_hash(Path(__file__)),
        "outcome_files": {m: file_hash(args.results / (m + ".jsonl")) for m in MODELS},
        "comparisons": {},
    }
    for model in MODELS[1:]:
        candidate = models[model]
        if baseline.keys() != candidate.keys():
            raise ValueError("Model outcomes use different subsets")
        results = {}
        for dataset in sorted({r["dataset"] for r in baseline.values()}):
            ids = [key for key, row in baseline.items() if row["dataset"] == dataset]
            paired = []
            exclusions = []
            for key in ids:
                a, b = baseline[key], candidate[key]
                if any(
                    a[field] != b[field]
                    for field in (
                        "prompt_sha256",
                        "reference_sha256",
                        "max_tokens",
                        "stratum",
                        "prompt_tokens",
                    )
                ):
                    raise ValueError("Paired inputs/tokenization differ")
                if (
                    a["status"] == b["status"] == "completed"
                    and a["score"]["status"] == b["score"]["status"] == "scored"
                ):
                    paired.append((a, b))
                else:
                    exclusions.append(
                        {
                            "id": key,
                            "baseline_status": a["status"],
                            "candidate_status": b["status"],
                        }
                    )
            result = {
                "selected": len(ids),
                "excluded": exclusions,
                "paired_coverage": len(paired) / len(ids),
                "answer": None,
                "strict": None,
            }
            if paired:
                for name, field in [
                    ("answer", "answer_correct"),
                    ("strict", "strict_correct"),
                ]:
                    result[name] = paired_comparison(
                        [a["score"][field] for a, _ in paired],
                        [b["score"][field] for _, b in paired],
                    )
            results[dataset] = result
        report["comparisons"][model] = results
    (args.results / "paired-comparison.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print("Saved per-task paired comparisons; automatic qualification remains disabled")


if __name__ == "__main__":
    main()

"""Render measured dataset study tables; refuse incomplete evidence."""

import argparse
import json
from pathlib import Path

from lattice.config import file_hash

ROOT = Path(__file__).resolve().parents[1]
IDS = [
    "qwen2.5-0.5b-instruct-f16",
    "qwen2.5-0.5b-instruct-q8_0",
    "qwen2.5-0.5b-instruct-q4_k_m",
]
LABELS = ["FP16", "Q8_0", "Q4_K_M"]


def load(path):
    return json.loads((ROOT / path).read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "docs/dataset_results.md")
    args = parser.parse_args()
    corpus = load("benchmarks/results/dataset-intake-full-corpus-v1/summary.json")
    completion = load("benchmarks/results/dataset-quality-v1/completed.json")
    quality = load("benchmarks/results/dataset-quality-v1/summary.json")
    paired = load("benchmarks/results/dataset-quality-v1/paired-comparison.json")
    lengths = load("benchmarks/results/dataset-token-lengths-v1/summary.json")
    catalog = load("benchmarks/datasets/catalog-curated-v1.json")
    if (
        completion["models"] != IDS
        or set(corpus["models"]) != set(IDS)
        or set(quality) != set(IDS)
    ):
        raise ValueError("Incomplete precision comparison")
    for model in IDS:
        path = ROOT / "benchmarks/results/dataset-quality-v1" / (model + ".jsonl")
        if file_hash(path) != paired["outcome_files"][model]:
            raise ValueError("Paired comparison references different outcomes")
    lines = [
        "# Dataset intake study",
        "",
        f"The intake-v1 curated catalog contains **{catalog['prepared_records']:,} retained records: {catalog['task_records']:,} tasks and {catalog['article_documents']:,} WikiText article documents**. Nine external source families (ten configurations) and four authored suites are documented in [datasets.md](datasets.md). This is evaluation data, not model pretraining, an official leaderboard submission or proof of representative quality preservation.",
        "",
        "The independent audit verified every prepared file hash, schema, ID/prompt uniqueness and active cross-partition source-group isolation. All 10,400 original authored canonical responses passed their declared answer and strict scorer, but a separate semantic audit found 11 physically impossible inventory setups; the curated view excludes those 11 and retains 10,389 authored cases. Scorer-valid references were not sufficient to prove semantic validity. Code execution and official IFEval verification remain deferred. The original 22-task smoke and 32-chunk precision studies are preserved separately. All 600 selected model-study prompts, references and strata are identical in the curated view; none was quarantined.",
        "",
        "## Corpus loss",
        "",
        "Pinned native llama-perplexity evaluated all **1,167 full 256-token chunks** of exact WikiText-2 raw test text, scoring each chunk’s final half: nominally **149,376 scored tokens**, not all corpus tokens. Source weights, tokenizer, corpus, context, batch and thread settings match across representations. This protocol is not a leaderboard-equivalent PPL claim.",
        "",
        "| Representation | Measured PPL | Cross-entropy (nats) | PPL change vs FP16 |",
        "|---|---:|---:|---:|",
    ]
    for model, label in zip(IDS, LABELS, strict=True):
        item = corpus["models"][model]
        lines.append(
            f"| {label} | {item['perplexity']:.4f} | {item['cross_entropy_nats']:.6f} | {item['relative_ppl_change_vs_f16'] * 100:+.2f}% |"
        )
    lines += [
        "",
        "Commands, model/source/native-tool hashes and native uncertainty are in [full-corpus results](../benchmarks/results/dataset-intake-full-corpus-v1/summary.json). Native uncertainty is not a confidence interval for a precision ratio. Operational wall times included concurrent data preparation and are not speed benchmarks. These expanded corpus results do not overwrite the earlier subset study.",
        "",
        "## Frozen generated-answer study",
        "",
        "Before generation, 60 evaluation IDs per scoring-ready configuration were frozen: **600 cases per representation, 1,800 attempted model–case pairs**. Seed 84721, greedy temperature zero, pinned Qwen user chat template, 2,048-token context and task-specific output caps are fixed. Equal class/template/tier quotas differ from source-prevalence weighting. Prompt/reference/model hashes, actual token lengths, outputs, extraction decisions and exclusions are retained in [quality results](../benchmarks/results/dataset-quality-v1/manifest.json).",
        "",
        "Each cell reports answer-correct / scored, followed by strict-correct / scored. Answer correctness permits documented normalization/extraction; strict correctness also requires the declared response format. No heterogeneous aggregate accuracy is reported. Instruction exact-text rubrics require canonical whitespace and can reject other semantically valid responses; these are canonical-rubric scores, not complete semantic instruction-compliance judgments.",
        "",
        "| Configuration | FP16 answer; strict | Q8_0 answer; strict | Q4_K_M answer; strict |",
        "|---|---:|---:|---:|---:|",
    ]
    datasets = sorted(quality[IDS[0]])
    for dataset in datasets:
        cells = []
        for model in IDS:
            item = quality[model][dataset]
            cells.append(
                f"{item['answer_correct']}/{item['scored']}; {item['strict_correct']}/{item['scored']}"
            )
        lines.append("| " + dataset + " | " + " | ".join(cells) + " |")
    lines += [
        "",
        "No oversized input is truncated. Skips/errors are excluded from accuracy only with explicit selected/scored coverage below; length-limited **output** completions remain scored. Every exclusion ID/status and per-stratum outcome is retained. High math output-cap hit rates mean these are quality-at-fixed-output-budget observations, not unconstrained reasoning-accuracy estimates. Results on supported prompt lengths cannot be generalized to skipped long contexts.",
        "",
        "| Configuration | Selected/model | Scored FP16 / Q8 / Q4 | Excluded FP16 / Q8 / Q4 | Output-cap finishes FP16 / Q8 / Q4 |",
        "|---|---:|---:|---:|---:|",
    ]
    for dataset in datasets:
        items = [quality[m][dataset] for m in IDS]
        lines.append(
            f"| {dataset} | {items[0]['selected']} | "
            + " / ".join(str(i["scored"]) for i in items)
            + " | "
            + " / ".join(str(i["excluded"]) for i in items)
            + " | "
            + " / ".join(str(i["truncated_completions"]) for i in items)
            + " |"
        )
    lines += [
        "",
        "Wilson intervals and SQuAD-style token F1 are in [per-task summaries](../benchmarks/results/dataset-quality-v1/summary.json). Answer-only math, generated-choice science/commonsense, explicit-abstention span QA and procedural formatting are Lattice protocols, not official benchmark scores. Public source partitions do not establish absence of foundation-model contamination; authored templates are shared across policy partitions.",
        "",
        "## Paired precision differences",
        "",
        "Accuracy loss is FP16 correctness minus candidate correctness on identical scored IDs; positive means degradation. Intervals conservatively bound paired discordant probabilities using Bonferroni-adjusted exact Clopper-Pearson bounds. They remain nonzero-width when all observed pairs agree. Each task interval has at least nominal 95% coverage under independent identically distributed pair sampling; shared source groups, deliberately balanced strata and this fixed benchmark sample limit population interpretation. They are not simultaneous intervals across all tasks. McNemar diagnostics are unadjusted and are not used for policy promotion.",
        "",
        "| Configuration | Q8 answer loss, 95% interval (pp) | Q4 answer loss, 95% interval (pp) |",
        "|---|---:|---:|",
    ]
    for dataset in datasets:
        cells = []
        for model in IDS[1:]:
            item = paired["comparisons"][model][dataset]["answer"]
            if item is None:
                cells.append("Unavailable")
            else:
                low, high = item["accuracy_loss_interval95"]
                cells.append(
                    f"{item['accuracy_loss_vs_baseline'] * 100:+.2f} [{low * 100:+.2f}, {high * 100:+.2f}]"
                )
        lines.append("| " + dataset + " | " + " | ".join(cells) + " |")
    lines += [
        "",
        "Full answer/strict paired counts, interval method, input checks and coverage are in [paired comparisons](../benchmarks/results/dataset-quality-v1/paired-comparison.json). These samples cannot establish a one-percentage-point noninferiority tolerance. **No routing policy, controller threshold or automatic precision qualification changes.** PPL point estimates alone do not establish quality preservation; the existing rejection/unqualified precision gates remain in force.",
        "",
        "## Measured prompt-length compatibility",
        "",
        f"All **{lengths['records']:,} original authored prompts** were tokenized through the pinned Qwen user chat template (`add_special=true`, `parse_special=true`). Row tiers are not token counts. Measurements establish tokenizer/context compatibility, not answer quality or throughput. Exact per-record lengths and prompt hashes are in [length results](../benchmarks/results/dataset-token-lengths-v1/lengths.jsonl).",
        "",
        "| Suite / nominal retrieval rows | Prompts | Minimum tokens | P50 tokens | Maximum tokens | Exceed 2,048 with 32 output tokens |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for group, item in lengths["groups"].items():
        lines.append(
            f"| {group} | {item['records']} | {item['minimum']} | {item['p50']:.1f} | {item['maximum']} | {item['exceeds_2k_with_32_output_tokens']} |"
        )
    lines += [
        "",
        "Length measurements include the original 11 later-quarantined inventory questions and do not make them valid tasks. The 32-token reserve in this compatibility table is an explicitly chosen inspection setting; the generated-answer study uses its own fixed per-task caps. Large retrieval tiers are retained as future-context data, not reported as successful 2k-context evaluations.",
        "",
        "## Reproduction and limitations",
        "",
        "Commands and source-specific licenses are in [datasets.md](datasets.md). Execute the corpus, quality and tokenizer studies sequentially; run `scripts/compare_dataset_quality.py` and `scripts/report_dataset_study.py` after completion. No GPU, energy, latency or memory improvement is established by these data-intake studies. Native CPU execution is real; no mocked GPU results are counted. HumanEval/MBPP pass@k, official IFEval, trained routing, broader model families, calibrated populations and representative quality-preservation claims remain unavailable.",
        "",
    ]
    args.output.write_text("\n".join(lines))
    print(args.output)


if __name__ == "__main__":
    main()

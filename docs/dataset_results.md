# Dataset intake study

The intake-v1 curated catalog contains **193,630 retained records: 192,884 tasks and 746 WikiText article documents**. Nine external source families (ten configurations) and four authored suites are documented in [datasets.md](datasets.md). This is evaluation data, not model pretraining, an official leaderboard submission or proof of representative quality preservation.

The independent audit verified every prepared file hash, schema, ID/prompt uniqueness and active cross-partition source-group isolation. All 10,400 original authored canonical responses passed their declared answer and strict scorer, but a separate semantic audit found 11 physically impossible inventory setups; the curated view excludes those 11 and retains 10,389 authored cases. Scorer-valid references were not sufficient to prove semantic validity. Code execution and official IFEval verification remain deferred. The original 22-task smoke and 32-chunk precision studies are preserved separately. All 600 selected model-study prompts, references and strata are identical in the curated view; none was quarantined.

## Corpus loss

Pinned native llama-perplexity evaluated all **1,167 full 256-token chunks** of exact WikiText-2 raw test text, scoring each chunk’s final half: nominally **149,376 scored tokens**, not all corpus tokens. Source weights, tokenizer, corpus, context, batch and thread settings match across representations. This protocol is not a leaderboard-equivalent PPL claim.

| Representation | Measured PPL | Cross-entropy (nats) | PPL change vs FP16 |
|---|---:|---:|---:|
| FP16 | 17.4152 | 2.857343 | +0.00% |
| Q8_0 | 17.5250 | 2.863628 | +0.63% |
| Q4_K_M | 18.0919 | 2.895464 | +3.89% |

Commands, model/source/native-tool hashes and native uncertainty are in [full-corpus results](../benchmarks/results/dataset-intake-full-corpus-v1/summary.json). Native uncertainty is not a confidence interval for a precision ratio. Operational wall times included concurrent data preparation and are not speed benchmarks. These expanded corpus results do not overwrite the earlier subset study.

## Frozen generated-answer study

Before generation, 60 evaluation IDs per scoring-ready configuration were frozen: **600 cases per representation, 1,800 attempted model–case pairs**. Seed 84721, greedy temperature zero, pinned Qwen user chat template, 2,048-token context and task-specific output caps are fixed. Equal class/template/tier quotas differ from source-prevalence weighting. Prompt/reference/model hashes, actual token lengths, outputs, extraction decisions and exclusions are retained in [quality results](../benchmarks/results/dataset-quality-v1/manifest.json).

Each cell reports answer-correct / scored, followed by strict-correct / scored. Answer correctness permits documented normalization/extraction; strict correctness also requires the declared response format. No heterogeneous aggregate accuracy is reported. Instruction exact-text rubrics require canonical whitespace and can reject other semantically valid responses; these are canonical-rubric scores, not complete semantic instruction-compliance judgments.

| Configuration | FP16 answer; strict | Q8_0 answer; strict | Q4_K_M answer; strict |
|---|---:|---:|---:|---:|
| arc_challenge | 22/60; 22/60 | 26/60; 25/60 | 25/60; 24/60 |
| arc_easy | 31/60; 31/60 | 30/60; 30/60 | 32/60; 31/60 |
| boolq | 32/60; 0/60 | 31/60; 0/60 | 31/60; 0/60 |
| commonsense_qa | 32/60; 32/60 | 33/60; 32/60 | 31/60; 25/60 |
| gsm8k | 6/60; 4/60 | 5/60; 3/60 | 5/60; 4/60 |
| lattice_arithmetic | 6/60; 0/60 | 6/60; 0/60 | 5/60; 0/60 |
| lattice_instructions | 15/60; 15/60 | 11/60; 11/60 | 24/60; 24/60 |
| lattice_retrieval | 13/36; 13/36 | 14/36; 14/36 | 15/36; 15/36 |
| lattice_structured | 20/60; 0/60 | 23/60; 0/60 | 15/60; 0/60 |
| squad_v2 | 18/60; 16/60 | 18/60; 15/60 | 17/60; 15/60 |

No oversized input is truncated. Skips/errors are excluded from accuracy only with explicit selected/scored coverage below; length-limited **output** completions remain scored. Every exclusion ID/status and per-stratum outcome is retained. High math output-cap hit rates mean these are quality-at-fixed-output-budget observations, not unconstrained reasoning-accuracy estimates. Results on supported prompt lengths cannot be generalized to skipped long contexts.

| Configuration | Selected/model | Scored FP16 / Q8 / Q4 | Excluded FP16 / Q8 / Q4 | Output-cap finishes FP16 / Q8 / Q4 |
|---|---:|---:|---:|---:|
| arc_challenge | 60 | 60 / 60 / 60 | 0 / 0 / 0 | 0 / 0 / 0 |
| arc_easy | 60 | 60 / 60 / 60 | 0 / 0 / 0 | 0 / 0 / 0 |
| boolq | 60 | 60 / 60 / 60 | 0 / 0 / 0 | 0 / 0 / 0 |
| commonsense_qa | 60 | 60 / 60 / 60 | 0 / 0 / 0 | 0 / 0 / 0 |
| gsm8k | 60 | 60 / 60 / 60 | 0 / 0 / 0 | 19 / 19 / 13 |
| lattice_arithmetic | 60 | 60 / 60 / 60 | 0 / 0 / 0 | 48 / 48 / 51 |
| lattice_instructions | 60 | 60 / 60 / 60 | 0 / 0 / 0 | 0 / 0 / 4 |
| lattice_retrieval | 60 | 36 / 36 / 36 | 24 / 24 / 24 | 0 / 0 / 0 |
| lattice_structured | 60 | 60 / 60 / 60 | 0 / 0 / 0 | 0 / 0 / 0 |
| squad_v2 | 60 | 60 / 60 / 60 | 0 / 0 / 0 | 0 / 0 / 1 |

Wilson intervals and SQuAD-style token F1 are in [per-task summaries](../benchmarks/results/dataset-quality-v1/summary.json). Answer-only math, generated-choice science/commonsense, explicit-abstention span QA and procedural formatting are Lattice protocols, not official benchmark scores. Public source partitions do not establish absence of foundation-model contamination; authored templates are shared across policy partitions.

## Paired precision differences

Accuracy loss is FP16 correctness minus candidate correctness on identical scored IDs; positive means degradation. Intervals conservatively bound paired discordant probabilities using Bonferroni-adjusted exact Clopper-Pearson bounds. They remain nonzero-width when all observed pairs agree. Each task interval has at least nominal 95% coverage under independent identically distributed pair sampling; shared source groups, deliberately balanced strata and this fixed benchmark sample limit population interpretation. They are not simultaneous intervals across all tasks. McNemar diagnostics are unadjusted and are not used for policy promotion.

| Configuration | Q8 answer loss, 95% interval (pp) | Q4 answer loss, 95% interval (pp) |
|---|---:|---:|
| arc_challenge | -6.67 [-17.69, +5.55] | -5.00 [-23.96, +14.71] |
| arc_easy | +1.67 [-7.02, +10.17] | -1.67 [-22.08, +18.99] |
| boolq | +1.67 [-7.02, +10.17] | +1.67 [-13.85, +16.89] |
| commonsense_qa | -1.67 [-12.84, +9.89] | +1.67 [-13.85, +16.89] |
| gsm8k | +1.67 [-7.02, +10.17] | +1.67 [-13.85, +16.89] |
| lattice_arithmetic | +0.00 [-7.04, +7.04] | +1.67 [-9.89, +12.84] |
| lattice_instructions | +6.67 [-5.55, +17.69] | -15.00 [-28.28, +0.74] |
| lattice_retrieval | -2.78 [-20.69, +15.99] | -5.56 [-27.82, +18.21] |
| lattice_structured | -5.00 [-15.34, +6.24] | +8.33 [-4.74, +19.93] |
| squad_v2 | +0.00 [-7.04, +7.04] | +1.67 [-7.02, +10.17] |

Full answer/strict paired counts, interval method, input checks and coverage are in [paired comparisons](../benchmarks/results/dataset-quality-v1/paired-comparison.json). These samples cannot establish a one-percentage-point noninferiority tolerance. **No routing policy, controller threshold or automatic precision qualification changes.** PPL point estimates alone do not establish quality preservation; the existing rejection/unqualified precision gates remain in force.

## Measured prompt-length compatibility

All **10,400 original authored prompts** were tokenized through the pinned Qwen user chat template (`add_special=true`, `parse_special=true`). Row tiers are not token counts. Measurements establish tokenizer/context compatibility, not answer quality or throughput. Exact per-record lengths and prompt hashes are in [length results](../benchmarks/results/dataset-token-lengths-v1/lengths.jsonl).

| Suite / nominal retrieval rows | Prompts | Minimum tokens | P50 tokens | Maximum tokens | Exceed 2,048 with 32 output tokens |
|---|---:|---:|---:|---:|---:|
| lattice_arithmetic:all | 4000 | 53 | 66.0 | 75 | 0 |
| lattice_instructions:all | 2400 | 44 | 66.5 | 83 | 0 |
| lattice_retrieval:128 | 320 | 2258 | 2417.0 | 3021 | 320 |
| lattice_retrieval:16 | 320 | 328 | 370.0 | 466 | 0 |
| lattice_retrieval:256 | 320 | 4475 | 4765.5 | 5874 | 320 |
| lattice_retrieval:32 | 320 | 610 | 655.5 | 828 | 0 |
| lattice_retrieval:64 | 320 | 1160 | 1236.0 | 1551 | 0 |
| lattice_structured:all | 2400 | 74 | 86.0 | 160 | 0 |

Length measurements include the original 11 later-quarantined inventory questions and do not make them valid tasks. The 32-token reserve in this compatibility table is an explicitly chosen inspection setting; the generated-answer study uses its own fixed per-task caps. Large retrieval tiers are retained as future-context data, not reported as successful 2k-context evaluations.

## Reproduction and limitations

Commands and source-specific licenses are in [datasets.md](datasets.md). Execute the corpus, quality and tokenizer studies sequentially; run `scripts/compare_dataset_quality.py` and `scripts/report_dataset_study.py` after completion. No GPU, energy, latency or memory improvement is established by these data-intake studies. Native CPU execution is real; no mocked GPU results are counted. HumanEval/MBPP pass@k, official IFEval, trained routing, broader model families, calibrated populations and representative quality-preservation claims remain unavailable.

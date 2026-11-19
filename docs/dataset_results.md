# Dataset intake study

The intake-v1 catalog contains 193,641 exported records: 192,895 tasks and 746 WikiText article documents. See [data cards, licensing and reproduction](datasets.md). The independent audit validated every prepared file hash, record schema, ID/prompt uniqueness and active cross-partition source-group isolation; every authored canonical response passed its declared answer/strict scorer. Those are data-integrity checks, not proof of representative model quality.

The original smoke/32-chunk precision study remains preserved. The expanded studies below use distinct versioned result folders and do not replace or relabel prior observations.

## Corpus loss

`experiments/datasets/full_corpus.py` runs the pinned native llama-perplexity tool sequentially on all 1,167 full 256-token chunks of the exact WikiText-2 raw test text. Native default scoring covers the final half of each chunk: nominally 149,376 scored tokens, not all corpus tokens. Checkpoint source, tokenizer, corpus, context, batch and thread settings are controlled across FP16, Q8_0 and Q4_K_M. Full commands/artifact hashes and native uncertainty are retained in `benchmarks/results/dataset-intake-full-corpus-v1/`.

The run is in progress; completed native results will be reported after all representations finish. Operational wall times include concurrent data preparation and are not latency/speed comparisons. Native PPL uncertainty is not a confidence interval for a precision ratio; this protocol is not a leaderboard-equivalent perplexity claim.

## Frozen generated-answer study

`experiments/datasets/quality_baseline.py` uses 60 preselected evaluation cases from each of ten scoring-ready configurations (600 per representation), fixed seed 84721, temperature zero, pinned Qwen user chat template and 2,048-token context. Caps vary by task and are fixed before observations. Long prompts are explicitly skipped without truncation; output-cap finishes remain in the score denominator. Source hashes, prompt/reference hashes, actual token counts, model artifacts, outputs, score extraction details, exclusions and per-stratum outcomes are retained.

Class/template-balanced selection is not source-prevalence weighting. Generated-choice, answer-only mathematics, explicit-abstention span QA and procedural formatting scores are Lattice protocols, not official leaderboard submissions. HumanEval/MBPP execution and official IFEval verification remain unavailable. Public-data contamination and template generalization remain unproven. Confidence bounds from these subsets cannot establish a one-percentage-point quality tolerance.

Results are not yet available. No controller threshold, routing policy or automatic precision qualification changes as part of this intake.

## Prompt-length compatibility

`experiments/datasets/token_lengths.py` measures all 10,400 authored prompts through the pinned Qwen chat tokenizer, recording exact input bytes and chat prompt tokens without generating output. Retrieval row tiers are never substituted for token lengths. Measurements will show which data exceed the current runtime context; this establishes length compatibility only, not long-context answer quality.

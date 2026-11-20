# Separate 1.5B model dataset observations

This study adds real responses from the existing explicit `qwen2.5-1.5b-instruct-q8` model to the same 600 frozen evaluation cases used by the 0.5B precision study. **Different weights and parameter count: this is not a same-checkpoint optimization comparison, validated model routing or a latency/cost improvement claim.** The original task count does not increase.

Model/source/binary hashes, fixed caps/sampling, actual token counts, outputs and licensing remain in [the separate quality folder](../benchmarks/results/dataset-quality-1.5b-v1/manifest.json). Tokenizer metadata match across these Qwen checkpoints: **true**. Every paired input prompt/reference/cap/token count was checked.

| Configuration | 0.5B Q8 answer / scored; strict / scored | 1.5B Q8 answer / scored; strict / scored | 1.5B exclusions |
|---|---:|---:|---:|
| arc_challenge | 26/60; 25/60 | 50/60; 50/60 | 0 |
| arc_easy | 30/60; 30/60 | 53/60; 53/60 | 0 |
| boolq | 31/60; 0/60 | 45/60; 0/60 | 0 |
| commonsense_qa | 33/60; 32/60 | 42/60; 42/60 | 0 |
| gsm8k | 5/60; 3/60 | 5/60; 5/60 | 0 |
| lattice_arithmetic | 6/60; 0/60 | 6/60; 1/60 | 0 |
| lattice_instructions | 11/60; 11/60 | 37/60; 37/60 | 0 |
| lattice_retrieval | 14/36; 14/36 | 22/36; 22/36 | 24 |
| lattice_structured | 23/60; 0/60 | 30/60; 0/60 | 0 |
| squad_v2 | 18/60; 15/60 | 30/60; 26/60 | 0 |

Accuracy uses the same documented Lattice generated-answer/canonical-rubric protocols, not official leaderboard scores. Long inputs are skipped explicitly, never truncated; length-limited outputs remain scored. Per-task intervals, strata and output-cap finishes are in [summaries](../benchmarks/results/dataset-quality-1.5b-v1/summary.json). Conservative paired differences and exclusions are in [different-model-comparison.json](../benchmarks/results/dataset-quality-1.5b-v1/different-model-comparison.json). Public benchmark contamination, related-source correlation and small balanced samples limit generalization. No automatic model-substitution policy is qualified.

## Additional corpus observation

The separate 1.5B model measured **PPL 11.9077** (cross-entropy 2.477185 nats) on a **predeclared first-256-chunk subset**, context 256, scoring the native final half of each chunk: nominally 32,768 tokens. Cross-entropy is derived as ln of the rounded reported PPL. This is a subset, unlike the primary 0.5B study’s 1,167 chunks. Do not compare these PPL point estimates as if their evaluation scopes were identical.

[Native command, hashes, uncertainty and subset declaration](../benchmarks/results/dataset-intake-1.5b-corpus-subset-v1/summary.json) are preserved. Operational wall times are not controlled latency/throughput measurements; no quality-cost routing conclusion follows from this observation alone.

See [data methodology and errata](datasets.md) and [the primary precision study](dataset_results.md).

# Lattice datasets

The versioned [dataset documentation](../../docs/datasets.md) describes nine external source families (ten configurations), four authored suites, licensing, splits, scorers and reproducible preparation. The recommended [catalog-curated-v1.json](catalog-curated-v1.json) records **193,630 curated records: 192,884 tasks and 746 WikiText article documents**. The original [catalog-v1.json](catalog-v1.json) preserves 193,641 exports; 11 impossible physical-inventory questions are explicitly quarantined in the curated view. [sources.lock.json](sources.lock.json) pins external artifacts; [eval-subsets-v1.json](eval-subsets-v1.json) freezes 600 selected evaluation IDs across ten scoring-ready configurations.

All 600 selected cases are byte-identical in [the curated subsets](eval-subsets-curated-v1.json); none was quarantined.

External raw/prepared data and large generated exports are gitignored. Rebuild them with the documented commands; all raw hashes/revisions and per-record source terms are preserved. [examples](examples/) contains small Apache-2.0 authored samples; it does not mirror third-party datasets. Code and official IFEval data are collected but their execution/official scorers remain deferred. Data availability is not a benchmark result or model-quality guarantee.

The original `quality-smoke.json` (22 tasks) and `corpus-smoke.txt` remain unchanged. These Apache-2.0 public fixtures test instrumentation and static task rubrics; they are not representative benchmarks or held-out quality evidence. Corpus repeats are disclosed and unsuitable for general language-quality claims. The old coding rubric parses AST without executing output.

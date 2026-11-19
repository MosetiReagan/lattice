# Versioned evaluation data

Lattice's intake-v1 contains **nine external source families (ten configurations), four authored suites, 192,895 task records and 746 WikiText article documents**. Total exported records: **193,641**. Of the task records, **191,219 have implemented generated-answer scorers**; 1,135 code tasks and 541 official IFEval tasks retain explicit deferred scorers. The old 22-task smoke suite remains separate and unchanged. Counts do not imply independent statistical samples, model training data, benchmark results or permission to relicense upstream content.

The machine-readable [catalog](../benchmarks/datasets/catalog-v1.json) records counts, class/template distributions and SHA-256 of every prepared file. [Source lock](../benchmarks/datasets/sources.lock.json) records immutable revisions, raw sizes, hashes, upstream URLs, attribution and licensing basis. External/raw/prepared data and large authored exports stay outside git; recipes, compact authored examples and [intake manifests](../benchmarks/datasets/manifests/) are tracked.

| Dataset/configuration | Development | Validation | Evaluation | Unit / status |
|---|---:|---:|---:|---|
| GSM8K | 5,955 | 1,518 | 1,319 | Numeric QA |
| ARC-Easy | 1,792 | 1,019 | 2,376 | Generated-choice science QA |
| ARC-Challenge | 890 | 519 | 1,172 | Same ARC source family |
| BoolQ | 6,372 | 1,621 | 3,270 | Passage yes/no |
| CommonsenseQA | 7,797 | 1,944 | 1,221 | Generated-choice QA |
| SQuAD 2 | 101,051 | 29,131 | 11,852 | Span/abstention QA |
| IFEval | 302 | 137 | 102 | Official verifier deferred |
| HumanEval | 0 | 0 | 164 | Execution scorer deferred |
| MBPP full | 306 | 165 | 500 | Execution scorer deferred |
| Lattice arithmetic | 2,400 | 800 | 800 | Procedural numeric gold |
| Lattice structured | 1,440 | 480 | 480 | Typed JSON gold |
| Lattice instructions | 1,440 | 480 | 480 | Explicit procedural constraints |
| Lattice retrieval | 960 | 320 | 320 | Exact lookup/pointer/abstention/version |
| WikiText-2 raw | — | — | — | 746 article documents across source splits; corpus loss |

Sources contain 23 selected files totaling **36,283,102 raw bytes**. Normalization produced 184,860 valid records, retained 183,241 and quarantined 1,619. WikiText's 44,836 raw rows are fragments/paragraphs; counting them as independent question-answer examples would be misleading. The normalized article count includes all source splits; corpus evaluation uses the original exact test text separately.

## Licensing and attribution

Each record retains its source license; Apache-2.0 applies to original Lattice code and authored suites, not all gathered data. Dataset cards and notices are snapshotted in [source_audit](../benchmarks/datasets/source_audit/README.md). The lock includes exact source-card URLs and SHA-256. Metadata reflects upstream declarations, not a new ownership claim.

| Source | Declared dataset terms | Upstream |
|---|---|---|
| GSM8K | MIT | [OpenAI](https://huggingface.co/datasets/openai/gsm8k) |
| ARC | CC-BY-SA-4.0 | [AI2](https://huggingface.co/datasets/allenai/ai2_arc) |
| BoolQ | CC-BY-SA-3.0 | [Google](https://huggingface.co/datasets/google/boolq) |
| CommonsenseQA | MIT | [CommonsenseQA authors](https://huggingface.co/datasets/tau/commonsense_qa) |
| IFEval | Apache-2.0 | [Google](https://huggingface.co/datasets/google/IFEval) |
| HumanEval | MIT | [OpenAI](https://huggingface.co/datasets/openai/openai_humaneval) |
| MBPP | CC-BY-4.0 | [Google Research](https://huggingface.co/datasets/google-research-datasets/mbpp) |
| WikiText | CC-BY-SA-3.0 OR GFDL | [WikiText authors / Wikipedia contributors](https://huggingface.co/datasets/Salesforce/wikitext) |
| SQuAD 2 | CC-BY-SA-4.0 | [SQuAD authors / Wikipedia contributors](https://huggingface.co/datasets/rajpurkar/squad_v2) |

HellaSwag was excluded: its inspected HF card did not specify licensing, and upstream returned HTTP 451. Winogrande's upstream README distinguishes Apache-2.0 **code** from CC-BY **data** without a version; the dataset is excluded pending clarification. OpenBookQA declares unknown licensing in inspected metadata. SocialIQA lacked license metadata and required a remote-code loader. Unlabeled external test splits are excluded; no model invents missing labels. Overlapping Winogrande subsets and the MBPP sanitized mirror are not additional independent datasets.

## Reference and split validation

Parquet/JSONL are read as data; no remote dataset Python executes. Adapters remap ARC numeric answer keys to displayed letters, require actual BoolQ booleans, extract GSM8K's explicit final-answer delimiter and verify every SQuAD answer against its exact context offset. Code references/tests are parsed as syntax only, never executed or counted as passing solutions.

Official test is the evaluation partition. If no labeled test is available, official validation becomes evaluation. Remaining training groups split deterministically 80/20 between development and validation; train-only IFEval uses 60/20/20. Related passage/article/question groups stay together. Hash-based group splits need not yield exact row percentages. Original source split/revision/row remains attached to every record.

Preparation quarantined: ARC 3 exact duplicates and 16 group-overlap rows; BoolQ 1,434 passage-overlap rows; MBPP 3 overlapping groups; SQuAD 124 rows with differing reference payloads for identical prompts plus 34 exact duplicates; WikiText 5 duplicate documents. Differing SQuAD references may be legitimate alternative annotations; Lattice conservatively quarantines them rather than guessing or declaring the source incorrect. Full removed records/reasons remain in the local audit SQLite database. Zero invalid references were emitted. A second complete preparation reproduced all 26 external JSONL file hashes and quarantine counts; a second full authored generation reproduced all 12 authored file hashes. Compact verification reports are retained with the intake manifests; temporary duplicate exports were removed and never counted as new data. The independent catalog audit checks every exported hash, count, ID, prompt uniqueness and cross-partition group isolation.

These policy partitions are **not** evidence that foundation-model pretraining excluded public benchmark content. Synthetic templates also occur in all partitions; this is instance/domain separation, not held-out-template generalization. Training a controller on development data requires a separate, frozen policy-evaluation protocol; no policy is promoted by this intake.

## Authored suite cards

All four suites use seed 73021, version intake-v1, deterministic procedural references, no LLM labels, globally unique normalized prompts, and 60/20/20 partition quotas within each template/row-tier stratum. Every canonical response must pass both answer and strict scorers before export. Numeric operand domains are 100–999 development, 1000–1999 validation and 2000–4999 evaluation; some auxiliary constants intentionally overlap. Instance seeds and IDs are distinct. IDs in prompts support record transformations and are not evidence of greater linguistic diversity.

| Suite | Cases | Templates | Intended use / limitation |
|---|---:|---|---|
| Arithmetic | 4,000 | Binary integer arithmetic, linear equations, rational addition, inventory, unit conversion | Exact bounded rational checking; limited English templates, not a GSM8K replacement |
| Structured | 2,400 | Extraction, filter/sort, aggregates, type preservation, Unicode/escaping, nested sums | Exact typed JSON; object key order ignored; arrays ordered; no general schema-following claim |
| Instructions | 2,400 | Literal/case, word count, numbered lines, header/footer, keyword frequency/forbidden word, JSON | Whitespace words/nonempty lines and explicit constraints; not official IFEval |
| Retrieval | 1,600 | Direct key, one-hop pointer, absent key, highest-version override | 16/32/64/128/256 nominal record rows; exact values; synthetic task, not broad long-context comprehension |

The retrieval pointer/override cases add a row beyond the nominal base tier. Prompts are shuffled with deterministic RNG. Row counts are never labeled token lengths; actual Qwen chat-token lengths are measured separately. Long authored prompts may exceed the runtime's current 2,048-token context and must be explicitly skipped, never truncated into a different task. The catalog retains those cases for future compatible contexts.

## Scoring protocols

`src/lattice/data/scoring.py` distinguishes answer correctness, strict format correctness and unsupported/invalid-reference status. Versioned protocols are Lattice generated-answer evaluations, not official benchmark leaderboard protocols.

- `number_v1`: exact bounded Decimal/Fraction arithmetic; canonical numeric-only output for strict compliance. Answer scoring additionally permits explicit `####` or heuristic last-number extraction, which is labeled in each observation and can over-credit prose. No executable `eval`.
- `choice_v1`: anchored letter, explicit answer line or leading labeled option. No search for arbitrary capital letters. Report generated-choice accuracy, not likelihood-ranked benchmark accuracy.
- `boolean_v1`: anchored yes/no/true/false; strict requires lowercase yes/no. Explanatory text can be answer-correct but format-incorrect.
- `span_v1`: SQuAD-style normalized exact match and token F1 against all source alternatives; only explicit UNANSWERABLE maps to empty prediction. This generated-span protocol has no calibrated no-answer probability threshold.
- `json_v1`: whole JSON, with duplicate object keys and nonfinite constants rejected; booleans cannot equal numbers, arrays preserve order and object keys do not. Whole fenced JSON may be content-correct but fails strict compliance.
- `constraints_v1`: explicit exact text, JSON, word/line/case/prefix/suffix and keyword checks. `text_v1`: exact trimmed response.
- HumanEval/MBPP, official IFEval and corpus documents return unsupported from generated-answer scoring, with no accuracy denominator. Code execution, pass@k and official IFEval verification require separate implementation.

Frozen evaluation IDs select **60 cases per scoring-ready configuration, 600 total**. Selection is hash-ranked with seed 84721, equal round-robin quotas by class or authored template/tier. This balances classes, so aggregate results need not estimate original source-prevalence accuracy. Each source checksum, selected ID, prompt/reference checksum and stratum is frozen in [eval-subsets-v1.json](../benchmarks/datasets/eval-subsets-v1.json). Subsets were fixed before model generation. Accuracy uncertainty is reported by Wilson intervals per task, not by treating all heterogeneous tasks as one large benchmark. Paired precision differences use conservative Bonferroni-adjusted exact binomial bounds for discordant outcomes, plus an unadjusted exact McNemar diagnostic; even identical observed outcomes do not imply zero future degradation risk. These sample sizes cannot establish a one-percentage-point quality tolerance.

## Reproduction

Use a provisioned CPU environment and locked dependencies. Preserve every prior intake; preparation/generation/frozen-subset commands refuse overwrites. Download verification is idempotent and preserves its existing manifest timestamp/hash. The checked-in subset command uses `--verify`; omit it only when creating a newly versioned subset file. Data-file hashes and selected IDs reproduce; fresh manifest timestamps and their dependent provenance hashes can differ.

```bash
uv sync --frozen --extra dev --extra evaluation --extra provision
uv run --no-sync python scripts/fetch_dataset_sources.py
uv run --no-sync python scripts/prepare_dataset_catalog.py --version intake-v1
uv run --no-sync python scripts/generate_lattice_datasets.py --version intake-v1 --seed 73021
uv run --no-sync python scripts/audit_dataset_catalog.py
uv run --no-sync python scripts/freeze_dataset_eval.py --count 60 --seed 84721 --verify
uv run --no-sync python experiments/datasets/full_corpus.py
uv run --no-sync python experiments/datasets/quality_baseline.py
uv run --no-sync python experiments/datasets/token_lengths.py
uv run --no-sync python scripts/compare_dataset_quality.py
uv run --no-sync python scripts/report_dataset_study.py
uv run --no-sync pytest -q -m 'not integration'
```

Use the checked-in source lock to reproduce. `lock_dataset_sources.py --output NEW_LOCK.json` discovers a new candidate lock and pinned cards for explicit review; it does not reproduce this intake and its hardcoded license expectations are not automatic legal validation of future upstream changes. Re-locking requires inspection before download.

The prepared JSONL plus raw downloads require roughly 400 MiB; full audit SQLite (including preserved rows/JSON and indices) adds roughly 523 MiB on this machine. Authored active exports add roughly 13 MiB; model weights/native binaries are separate. Downloader reserves 3 GiB free disk. CPU quality evaluation runs model variants sequentially and avoids overlapping corpus-loss jobs; operational wall times are not speed benchmarks. See [dataset study results](dataset_results.md) for measured outcomes and remaining exclusions.

Optional separate model observations use `experiments/datasets/larger_model_quality.py` and `experiments/datasets/larger_model_corpus.py` after the primary studies finish. These use the explicit registered Qwen 1.5B Q8 checkpoint and preserve separate result folders. They are different-model observations, not same-checkpoint optimization results or validated routing. They do not add new task records to the catalog.

`scripts/export_dataset_observations.py --include-larger-model` exports completed measured model–case outcomes as CSV/JSONL with source hashes and per-row licensing. These frozen evaluation outcomes must not become controller training or threshold-tuning data. Multiple representations answering one case add observations, not task records. Operational duration fields are not isolated cost/latency labels.

# Proposed reproducible baseline protocol

Status: protocol only; no benchmark runner or results yet. Freeze the Phase C baseline before introducing optimization code. First Phase B smoke test is not a speed result.

## Artifact and machine lock

Record OS/kernel, CPU flags/core quota, thread affinity, RAM/swap, host load, runtime/compiler versions, backend commit/binary SHA-256/build flags, model revision/conversion/hash, tokenizer assets/chat-template hashes and complete launch arguments. Pin source dependencies, model revisions and dataset revisions; do not use mutable `latest` downloads in published runs. Resolve the llama.cpp release candidate against its actual commit, build it, then verify flags from that binary. Keep commands, stderr/stdout and raw records. No benchmark is reproducible until these exact artifacts and prompt files are present.

First configuration: Qwen2.5-0.5B-Instruct converted once from pinned BF16 safetensors to F16 GGUF; CPU-only, 4 inference threads, 4 prefill threads if supported, one slot, total context 2,048, fixed prefill batch/microbatch, F16 KV, speculation off, cross-request prompt reuse off. Retain normal within-request KV caching: disabling it creates an unfair standard baseline. Explicitly disable context shifting/truncation. Bind to loopback; use raw completion/token endpoints first to remove ambiguous chat-template overhead. Validate actual token counts through the model tokenizer.

Example intended sequence (verify pinned-version flags before execution):

```bash
llama-server --help
llama-bench --help
# Then save exact CPU-only server and benchmark invocations in the run manifest.
# Do not present placeholder model paths or untested flags as published commands.
```

No copy/paste reproduction claim is made until Phase C ships the artifact lock, workloads and working commands. The server README snapshot documents changed speculative flags; do not rely on old `--draft-max` recipes.

## Workload matrix

| Category | Proposed token inputs / requested outputs | Isolation |
|---|---|---|
| Short prompts / short responses | 32, 128 / 32 | One active request |
| Short prompts / long responses | 32, 128 / 128, 256 | One active request |
| Long prompts | 512, 1,536 / 32, 128 | Within 2,048 total context |
| Repeated prefix | 512 shared tokens + 32 unique / 64 | Cold and warm separated; exact prefix identity |
| Concurrent | 128 / 64 | Concurrency 1, 2, 4 within measured memory limits |
| Mixed | Fixed seeded mixture of above | Fixed arrival trace; report offered/accepted/completed work |
| Memory constrained | Fixed 128 / 64 then context sweep | Explicit worker limits; report rejection/OOM, not hidden truncation |

Store immutable prompt texts, token IDs, licenses and hashes. Synthetic token-length workloads measure performance, not useful language quality. Natural-language quality datasets remain separate. Performance runs may suppress EOS only as a declared synthetic workload setting applied identically to both arms; natural generation must preserve real stop behavior and report actual lengths. Never pad a shorter optimized completion with fake tokens.

## Trial design and fairness

For each configuration perform 3 warmups and at least 30 paired measured repetitions, randomizing AB/BA order and fixed prompt/seed assignments. Pilot first to choose feasible run duration; preregister any change. Repeat in three independent sessions to assess shared-VM noise. Measure loading separately with fresh workers; label filesystem-cold versus process-cold honestly (do not claim disk-cache control if unavailable). Steady-state runs exclude model load equally; routing that swaps models includes load in end-to-end cost.

Control checkpoint, tokenizer, input IDs, context, sampling transforms/order, seed, output cap, thread counts, memory limits, batch sizes, arrivals and warm-up. Greedy first: temperature 0, no stochastic truncation, repetition/frequency/presence penalties off, identical BOS/EOS. Quantization changes representation only, not source checkpoint. Model routing is a different-model experiment and cannot be labeled same-weight optimization. Record the complete resolved backend configuration; defaults can change.

Compare both unchanged backend defaults and a fixed tuned backend baseline. Individual ablations: speculation draft lengths 1/2/4/8 with Qwen pair; prefix reuse off/on; weight F16/Q8_0/Q4_K_M; cache F16/eligible lower precision; admission and routing separately. Do not combine optimizations before independent measurements. Disable incompatible paths explicitly and record reasons.

## Measurements and statistics

Use monotonic timestamps. Measure client queue time, load, backend prefill, TTFT, per-token intervals, decode and total latency separately when instrumentation permits. Client TTFT includes transport/tokenization and is not backend prefill. If chunks contain multiple tokens, chunk intervals cannot be called inter-token latency. Throughput uses actual generated tokens / appropriate elapsed interval; aggregate throughput uses workload makespan. Record RSS high-water mark and sampled memory including workers; disclose shared/mmap accounting and sampling resolution. GPU/energy metrics unavailable here.

Report sample count, mean, sample standard deviation, median/P50, P90/P95 and raw records. Report P99 only with >=1,000 completed observations and an uncertainty warning; default 30-trial experiments report unavailable. Use paired bootstrap confidence intervals for latency/resource differences and include all failed/time-limited requests in stability reports. Do not use fabricated timings, extrapolated GPU results or zero as missing data.

For speculation record proposed/accepted/rejected token counts, target forward passes, draft and verification latency and extra RSS, only where backend telemetry truly exposes them. Tokens per target forward requires actual pass instrumentation. Cache metrics need real byte accounting, hits/misses/evictions and prefix tokens saved; HTTP response caching is not KV reuse.

## Quality and acceptance

Greedy same-representation optimizations: exact token IDs required against the pinned baseline for supported deterministic conditions, with mismatches investigated and disclosed. Quantization and cross-model routing: evaluate held-out tasks and cross-entropy/perplexity on pinned corpus chunks with identical masking and tokenization; bits-per-byte uses actual UTF-8 byte counts and documented normalization. Cross-tokenizer perplexities are not directly comparable.

Include reasoning, math exact match, coding tests in a restricted worker, instruction rubric, JSON/schema correctness and long-context retrieval. Pin dataset revisions, licenses and scoring scripts; selecting their exact subsets and artifact hashes is a Phase C prerequisite, not completed here. No claim of comprehensive quality from a tiny smoke corpus. Avoid model-judge-only evidence; disclose judge configuration and uncertainty if used.

Proposed tolerances for review before optimization: same-weight greedy exactness; approximate paths at most 2% relative perplexity increase and at most 1 percentage-point task-score drop, with confidence intervals and sufficient sample size to assess these bounds. Each task stratum must pass; do not average away regressions. Margins are product choices, not established guarantees. Stochastic speculation needs finite-vocabulary correctness cases plus seeded repeated sampling with distribution tests/multiple-comparison control; identical seed/text alone proves nothing.

Accept an optimization only when quality noninferiority and at least one preregistered resource objective improve repeatably with uncertainty quantified. Record operational costs and negative results. Counterfactual replay evaluates policies on held-out profiles; then live randomized trials evaluate interactions. Unknown profiles cannot authorize automatic low-quality paths.

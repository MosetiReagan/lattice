# Competitive execution plan and first measurements

## Decision

The original frozen burst confirmation **failed the overall gate**. Its latency and throughput conditions passed against the frozen native8 baseline, but two Lattice responses differed from greedy baseline outputs (a third comparison mismatch involved the thin queue baseline). Strict copy-task correctness was 0/360 in every arm under raw completion framing. The later cache-budgeted v7 chat study passed a separately frozen, restricted synthetic-burst gate against both tuned native challengers; it does not alter the original failure or establish general superiority. See the [v7 confirmation](chat-cache-budget-confirmation-v7.md), [original confirmation](burst_admission_confirmation.md) and [original boundary diagnostics](admission_boundaries.md).

## Latest restricted confirmation — November 21

The cache-enabled candidate completed all three predeclared sessions and passed the v7 latency, throughput, exact-output/classification, actual-cache-path, memory, no-swap, cgroup-bandwidth and per-arm CPU-steal gates. Its interactive P95 ratio was 0.089 versus `native4_b64_noram` and 0.070 versus `native1_noram`; throughput ratios were 1.077 and 0.966, with the latter's 95% bootstrap interval [0.952, 0.979]. Every arm scored 352/360 strict copy tasks, with zero matched-output mismatches and zero failed requests. The fixed study therefore qualifies for this named trace/configuration only.

The measurements use Qwen2.5 0.5B FP16 on one shared four-vCPU VM; the three sessions are not independent hardware replications. All six earlier attempts remain documented: v1-v3 and v6 completed but failed CPU-steal eligibility, while v4-v5 did not start after failing preflight. The finalizer passed 171 tests, Ruff checks and packaging. No further confirmation was started after v7 passed, so the fixed sample plan remains intact.

The candidate's pooled interactive P95 was 4,843.5 ms versus 12,125.3 ms, with throughput 10.73 versus 9.64 tokens/s. The native throughput aggregate includes a large unexplained shared-VM slowdown; it must not be marketed as a reliable throughput gain. Interactive-only diagnostics lost throughput, and late-arriving short requests benefited less. Defaults stay unchanged.

The next development study uses the model's actual chat template on both arms, recorded before measurement, because instruction prompts submitted as raw completion continuations did not produce strict valid copy-task answers. It is separately versioned, uses new development/confirmation seeds, preserves the failed study, and retains exact-output and absolute task-quality checks. A framing change cannot retroactively rescue the failed gate. Numerical batching differences are a possible cause of the divergent continuations, not an established diagnosis.

The [chat development sweep](chat_admission_development.md) preserved outputs in its completed initial blocks, with 22/24 strict task correctness. Focused tuning was interrupted after sustained 74–75% CPU steal appeared. A separate four-worker probe received only 25.21% of requested CPU time. Those development records remain exploratory. A subsequent cache-budgeted held-out protocol passed its restricted gates; see [v7 confirmation](chat-cache-budget-confirmation-v7.md) and [environment history](benchmark_environment_concern.md). Host-aware preflight and per-arm CPU counters preserve eligibility evidence in both passing and failed sessions.

The subsequent [pinned one-thread sweep](single_cpu_admission_development.md) investigated the available lower-resource envelope. It retained output equality but did not establish clean host eligibility across all arms. Its separate single-CPU draft remains unexecuted. The cache-budgeted v7 confirmation used its own frozen cached candidate, two native challengers, cgroup budget and fresh held-out seeds; it passed only its named synthetic burst gates.

The first pilot does not establish a competitive speed advantage over matched direct llama.cpp. Standard single-slot execution is near parity, two-slot runtime overhead is measurable, and native prompt caching recovers essentially the same repeated-prefix benefit as Lattice's qualified cache path. These are engineering findings, not a reason to lower the original 1.0 gates or claim a win against a deliberately weak baseline.

The product hypothesis remains: preserve model quality while improving interactive tail latency under heterogeneous CPU workloads, within an explicit memory budget. V7 passed the frozen gates for one named synthetic burst and configuration. Broader workload prevalence, independent hardware replication and comparison beyond the tested native configurations remain open; this result does not establish industry-wide superiority.

## Completed baseline work

- Ran two matched single-slot blocks: five workloads, ten paired trials per workload per block, same Qwen 0.5B FP16 checkpoint, backend binary, threads, context, sampling and per-workload worker address-space caps. All 100 reported pairs had identical output token IDs. Earlier exploratory cap-label mismatch data are preserved separately and excluded.
- Ran two direct-native versus Lattice two-slot arrival-trace blocks, ten pairs per block. Model weights, slot count, context and caps matched. All 20 request pairs retained greedy equality. Lattice short-request P50 was about 11–16% slower than direct native calls in these pilots.
- Ran 30 three-arm repeated-prefix trials: direct uncached, direct native caching, and Lattice adaptive exact-prompt caching. Raw input framing is identical in the final run; all 30 triples match greedy outputs. Direct native caching is the relevant upstream baseline. Earlier mismatched-framing pilot data are retained and excluded.
- Historical one-slot/two-slot results are reclassified as upstream configuration/product-integration evidence. They are not evidence of a Lattice algorithm beating llama.cpp.

See [standard comparison](direct_lattice_comparison.md), [two-slot comparison](direct_lattice_batching_comparison.md), and [cache comparison](adaptive_native_cache_comparison.md).

## Iteration 1 — reduce control-plane overhead

Profile HTTP client construction/connection setup, template/tokenizer round trips, per-request cache-key construction, metrics/audit writes and slot-lease cleanup. Measure their shares before changing runtime code. Candidate improvements are lifecycle-managed reusable clients, fewer redundant preflight calls after verified identity matching, and lower-cost audit serialization. No optimization may bypass explicit limits, cross-tenant isolation, cancellation acknowledgement or source-model/sampler constraints.

Acceptance for this overhead iteration: greedy outputs and all limits remain unchanged; paired native-relative median overhead stays within 5% and P95 within 10% on both serial and two-slot traces in three randomized sessions. These are prospective targets, not achieved claims. Include client/control-plane RSS, startup and failed requests as well as worker RSS.

## Iteration 2 — test resource-aware admission

Only after overhead is characterized, compare existing priority/aging admission with FIFO on burst traces where both native slots are occupied. Freeze arrivals and explicit user classes/budgets; do not infer validated task complexity from prompt wording. Include interactive-only, long-only, and mixed 25/50/75% workloads, plus low/high offered load. A priority win must disclose long-request slowdown, queue starvation, makespan and rejection rates. Tuned direct-native slot counts and a simple priority baseline must be included: priority queueing is not unique intellectual contribution by itself.

Use held-out trace seeds and a separate development trace family. Do not choose the evaluation mix or thresholds after seeing favorable outcomes.

## Prospective competitive gate

The machine-readable [protocol](../benchmarks/workloads/competitive-gate-v1.json) freezes these targets. The first confirmation is reported as failed, with no change to these targets.

For a named workload class and fixed model, require at least 20% lower interactive P95 than the strongest matching tuned baseline, no more than 5% aggregate throughput loss, the same explicit worker/host memory budget, no additional failures or starvation, and matched deterministic outputs. Run at least three clean randomized sessions with confidence intervals clustered by session/trace. One session's favorable P95 is not sufficient. If using approximate precision/model substitution, preserve the existing <=2% relative PPL and <=1 percentage-point task-loss tolerances with adequate uncertainty; exact output equality cannot be assumed for those paths.

The current two-slot arrival test uses chat framing, leading to short EOS-stopped completions even when the cap is 128. It is not a sustained long-generation benchmark. Before evaluating scheduling, include prompts with measured long outputs, report actual completion lengths and never discard short EOS outcomes or silently force output length.

## Comparison boundaries

The machine has four CPU cores and approximately 7.8 GiB RAM; no accelerator has been tested. llama.cpp is the current directly runnable baseline. vLLM, SGLang, GPU/MPS engines, different model families and commercial endpoints are not covered by these measurements. Do not compare different hardware or claim an industry-wide win.

Model-quality competition is a separate study: select peer-size models with compatible licensing and tokenizer-aware metrics, then run independent quality/cost comparisons. Lattice does not become a stronger base model by changing the scheduler.

## Go/no-go

Keep release classification at 0.3.0.dev0. After overhead profiling and two scheduling iterations, review the prospective gate without changing it. If there is no useful quality/resource/latency trade-off against a strong tuned baseline, stop broadening the serving abstraction and narrow or pivot the project to the components that have independent measured value. No release, publication or policy promotion follows automatically from pilot data.

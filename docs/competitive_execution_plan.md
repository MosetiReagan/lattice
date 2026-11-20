# Competitive execution plan and first measurements

## Decision

The subsequent frozen burst confirmation **failed the overall gate**. Its latency and throughput conditions passed against the frozen native8 baseline, but two Lattice responses differed from greedy baseline outputs (a third comparison mismatch involved the thin queue baseline). Strict copy-task correctness was 0/360 in every arm under raw completion framing. These results do not establish a qualifying win. See [confirmation](burst_admission_confirmation.md) and [all boundary diagnostics](admission_boundaries.md).

The candidate's pooled interactive P95 was 4,843.5 ms versus 12,125.3 ms, with throughput 10.73 versus 9.64 tokens/s. The native throughput aggregate includes a large unexplained shared-VM slowdown; it must not be marketed as a reliable throughput gain. Interactive-only diagnostics lost throughput, and late-arriving short requests benefited less. Defaults stay unchanged.

The next development study uses the model's actual chat template on both arms, recorded before measurement, because instruction prompts submitted as raw completion continuations did not produce strict valid copy-task answers. It is separately versioned, uses new development/confirmation seeds, preserves the failed study, and retains exact-output and absolute task-quality checks. A framing change cannot retroactively rescue the failed gate. Numerical batching differences are a possible cause of the divergent continuations, not an established diagnosis.

The first pilot does not establish a competitive speed advantage over matched direct llama.cpp. Standard single-slot execution is near parity, two-slot runtime overhead is measurable, and native prompt caching recovers essentially the same repeated-prefix benefit as Lattice's qualified cache path. These are engineering findings, not a reason to lower the original 1.0 gates or claim a win against a deliberately weak baseline.

The product hypothesis remains: preserve model quality while improving interactive tail latency under heterogeneous CPU workloads, within an explicit memory budget. Evidence so far supports running the next focused engineering iteration, not publishing a superiority claim.

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

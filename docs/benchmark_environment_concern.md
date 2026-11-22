# Benchmark CPU availability concern

## Current decision

The frozen raw-completion study failed exact-output preservation. A later, separately versioned cache-budgeted chat study passed its restricted synthetic burst gate against both named native configurations; this does not establish general engine superiority or repair any earlier failed study. The v1-v3 and v6 cache-budgeted runs failed per-arm CPU-steal eligibility; v4-v5 stopped at preflight. All results remain separate.

## Cache-budgeted held-out result, November 21

Protocol v7 completed all three fixed sessions (30 paired traces, 360 responses per arm) under a 0.92-CPU cgroup and one pinned CPU. It passed every frozen gate: latency, throughput, exact token/text/prompt-length and task-classification agreement, actual cached execution, worker memory/no-swap, configured bandwidth and per-arm CPU-steal eligibility. The candidate's outputs matched both native challengers; strict copy-task correctness was 352/360 for each arm. P95 ratios were 0.089 against the native4 throughput challenger and 0.070 against native1. Throughput ratios were 1.077 and 0.966, respectively; the latter's fixed bootstrap lower bound was 0.952 against the 0.95 threshold.

This result is limited to the named Qwen2.5 0.5B FP16 synthetic burst, settings, prompts and shared four-vCPU VM. Sessions are not independent hardware replications. The accompanying [report](chat-cache-budget-confirmation-v7.md), [boundary diagnostics](chat-cache-budget-boundaries-v7.md), raw JSONL and per-arm CPU records retain the complete evidence. Earlier failed results and preflight failures remain unchanged.

## Observed environment evidence

On November 20, 2026, `vmstat` reported approximately 74–75% CPU steal during native four-thread execution around 23:37–23:39 UTC. The focused development block retained 13 completed arm/trace records and an explicit `interruption.json`; the in-flight arm was interrupted and is not a completed measurement. An isolated three-second, four-worker CPU-availability probe at 23:41:22 UTC measured:

| Quantity | Measured value |
|---|---:|
| Requested workers | 4 |
| Received CPU time / requested worker wall time | 25.21% |
| Whole-VM CPU steal fraction during probe | 73.68% |
| Host eligibility | Failed |

These are host diagnostics, not inference speed, energy or model-quality results. The probe's raw worker CPU/wall samples are in `benchmarks/results/host-availability-v1/probe-1.json`. No other model benchmark was running during this probe. The earlier 68-second native outlier has no matching CPU-steal history, so this later observation does not prove the cause of that earlier outlier.

A second isolated probe at 23:44:30 UTC again failed: 24.65% of requested CPU time and 72.11% aggregate CPU steal. Its independent raw samples are preserved in `probe-2.json`. CPU availability had not recovered at that check; no second held-out model study was started.

## Preserved engineering work

- Frozen raw study: 30 paired traces, three sessions, zero request failures, but two candidate-output mismatches and one thin-queue mismatch. The overall gate remains failed even though its performance conditions passed.
- Chat-framed development: the model's actual chat template was applied identically before timing. Completed initial blocks matched outputs across all tested configurations and scored 22/24 strict copy-task answers per arm. This is exploratory evidence, not held-out quality qualification or a fix for arbitrary batching-related divergence.
- Focused diagnostics retain unfavorable outcomes, including large slowdowns under contention. They cannot finalize a candidate/baseline selection or certify a clean CPU history for preceding development.
- Admission now bounds grace/drain waiters even before native slots are occupied. Defaults stay priority/FIFO with one slot.
- Current real CPU and mocked/control-plane suite: **159 passed**. These tests establish functionality in their tested scope, not a competitive performance win or GPU support.

## Eligibility and execution record

`scripts/check_benchmark_host.py` performs a bounded CPU probe. The prospective host preflight requires no more than 5% aggregate CPU steal and at least 90% of requested CPU time. A preflight is only a start condition; it does not guarantee future availability.

The chat runner records whole-VM CPU counters for each complete arm, including startup/warmup as well as measured requests. Every frozen confirmation requires each arm's aggregate steal <=5% and maximum sampled interval steal <=10%. Missing/reset counters are unavailable, never zero. A failed host gate disqualifies that complete study; do not exclude or rerun only contaminated traces.

The cache-budgeted v7 protocol completed its fixed three-session, 30-pair held-out run and passed all gates; the full [report](chat-cache-budget-confirmation-v7.md) and [boundary diagnostics](chat-cache-budget-boundaries-v7.md) include its scope and limitations. Earlier cache-budgeted v1-v3 and v6 runs completed but failed per-arm CPU-steal eligibility. V4-v5 did not start because their stricter preflights failed. None of these outcomes replaces or repairs another study.

The v7 preflight was eligible and its every-arm CPU records passed, while previous longer-run spikes show why preflight remains only a start condition. The project stays at unreleased `0.3.0.dev0`, with no release/tag or remote publication.

## Pinned single-CPU follow-up, November 21

A single-worker microprobe received 94.32% of requested CPU time, so development also tested one backend thread with the benchmark, controller and native workers pinned to virtual CPU 0. This is a separately documented resource envelope, with the same model/sampling/context/caps. It does not rescue the failed raw study or certify the original four-thread environment.

The complete [single-CPU development sweep](single_cpu_admission_development.md) tested native slots 1/2/4/8/16, additional native4 batch sizes 64/128/512/1024, a thin two-slot cost queue and Lattice two-slot coalescing. All eleven configurations preserved corresponding outputs and scored 10/12 strict copy-task answers on that development trace. The pinned pilot on a different development seed scored 12/12 in both arms.

The candidate's development interactive P95 was 3,487 ms versus 32,110 ms for the lowest-P95 native configuration. Its actual throughput was 0.883 tokens/s versus 0.903 tokens/s for the highest-throughput native configuration, about 2.2% lower. These are exploratory point estimates from a small development set, without held-out confidence or a winning claim.

Crucially, four of the eleven completed pinned development arms still exceeded the unchanged 10% sampled-interval CPU-steal limit; the highest was 13.8%, despite whole-arm means below 5%. All spikes and unfavorable measurements remain in the table/raw records. A passing three-second probe is not sufficient to certify a complete inference experiment. Consequently the fixed three-session confirmation budget was not launched on this unstable allocation.

The separate `chat-single-cpu-confirmation-v1.draft.json` remains an unexecuted draft. Its one-thread candidate/challenger sweep is preserved as development evidence; the passing v7 result used a distinct cache-enabled protocol and does not reclassify this draft or its measurements.

# Benchmark CPU availability concern

## Current decision

No qualifying competitor win is established. The frozen raw-completion study failed exact-output preservation. The separately prepared chat-framed study has not reached held-out confirmation: focused development was interrupted when sustained CPU steal made the configured four-vCPU environment unavailable. No failed or unfinished observation has been replaced with an estimate or relabeled as a success.

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

## Eligibility and next execution

`scripts/check_benchmark_host.py` performs a bounded CPU probe. The prospective host preflight requires no more than 5% aggregate CPU steal and at least 90% of requested CPU time. A preflight is only a start condition; it does not guarantee future availability.

The chat runner now records whole-VM CPU counters for each complete arm, including startup/warmup as well as measured requests. A future frozen confirmation must additionally require every arm's aggregate steal <=5% and maximum sampled interval steal <=10%. Missing/reset counters are unavailable, never zero. Any failed host gate disqualifies the complete study's win claim; do not exclude or rerun only contaminated traces.

The next protocol remains explicitly **draft** at `benchmarks/workloads/chat-burst-confirmation-v1.draft.json`. Its candidate/baseline choices are provisional. The executable runner refuses to start without a reviewed frozen protocol and a fresh passing host probe. No held-out chat seeds have been generated or measured. Complete a separately named development block on eligible CPU resources, freeze source/configuration and sample budget, then execute confirmation once and report every gate without relaxing thresholds. Do not run repeated confirmations until one happens to pass.

Resource availability is an outstanding prerequisite, not a successful result. The project stays at unreleased `0.3.0.dev0`, with no release/tag or remote publication.

## Pinned single-CPU follow-up, November 21

A single-worker microprobe received 94.32% of requested CPU time, so development also tested one backend thread with the benchmark, controller and native workers pinned to virtual CPU 0. This is a separately documented resource envelope, with the same model/sampling/context/caps. It does not rescue the failed raw study or certify the original four-thread environment.

The complete [single-CPU development sweep](single_cpu_admission_development.md) tested native slots 1/2/4/8/16, additional native4 batch sizes 64/128/512/1024, a thin two-slot cost queue and Lattice two-slot coalescing. All eleven configurations preserved corresponding outputs and scored 10/12 strict copy-task answers on that development trace. The pinned pilot on a different development seed scored 12/12 in both arms.

The candidate's development interactive P95 was 3,487 ms versus 32,110 ms for the lowest-P95 native configuration. Its actual throughput was 0.883 tokens/s versus 0.903 tokens/s for the highest-throughput native configuration, about 2.2% lower. These are exploratory point estimates from a small development set, without held-out confidence or a winning claim.

Crucially, four of the eleven completed pinned development arms still exceeded the unchanged 10% sampled-interval CPU-steal limit; the highest was 13.8%, despite whole-arm means below 5%. All spikes and unfavorable measurements remain in the table/raw records. A passing three-second probe is not sufficient to certify a complete inference experiment. Consequently the fixed three-session confirmation budget was not launched on this unstable allocation.

The separate `chat-single-cpu-confirmation-v1.draft.json` retains thirty paired traces and the 20% latency / 5% throughput targets. It names both the development latency leader and throughput leader as challengers, with the same conditions required against each. Host availability, zero failed requests and exact output preservation remain mandatory; no threshold or result is relaxed to manufacture a win. No held-out chat seeds have been generated or measured.

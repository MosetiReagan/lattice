# Chat-framed burst confirmation

This separately frozen study follows the failed raw-completion study; it does not overwrite or reclassify that failure. Each source instruction is rendered through the model's actual /apply-template endpoint before timing. Every arm receives identical rendered bytes, tokenizer, greedy sampler, output caps and exogenous arrivals. Template preparation and equal one-request warmup are excluded; reported latency includes admission grace, queueing and generation, not the full HTTP chat gateway.
Resource envelope: backend threads 1, CPU affinity [0], context 2048 tokens per request and 4096 MiB worker address-space cap. Worker/control-plane RSS and dispatch lateness are retained in analysis.json; control-plane RSS belongs to the common harness, not an isolated production gateway.

Restricted gate pass: **False**. Frozen gates: `{"host_cpu_eligibility": false, "latency": true, "quality_and_errors": true, "throughput": false, "worker_cap_and_no_swap": true}`.

| Baseline | Interactive P95 ms | Candidate P95 ms | Ratio [95% interval] | Baseline / candidate tokens/s | Throughput ratio [95% interval] |
|---|---:|---:|---|---|---|
| native4_b64 | 29879.9 | 2971.4 | 0.099 [0.068, 0.106] | 0.803 / 0.853 | 1.062 [1.049, 1.074] |
| native1 | 37826.2 | 2971.4 | 0.079 [0.054, 0.084] | 0.894 / 0.853 | 0.953 [0.942, 0.963] |

| Session | Interactive P95 ratio | Throughput ratio | Baseline / candidate bulk P95 ms |
|---|---:|---:|---|
| 1 | 0.097 | 1.072 | 42122.1 / 39125.2 |
| 2 | 0.072 | 1.066 | 41662.2 / 39066.3 |
| 3 | 0.100 | 1.049 | 41859.1 / 40113.1 |

There are 0 baseline-output/classification mismatches and 0 failed requests across 30 paired traces. Strict absolute copy-task correctness: native4_b64: 355/360; native1: 355/360; lattice_coalesce2: 355/360. No incorrect/EOS/cap-finished requests are excluded.

Both performance conditions must hold in every session and for 10,000 fixed-seed hierarchical paired bootstrap confidence bounds. No additional confirmation traces or relaxed thresholds are allowed after seeing the result. Three sessions share one four-core CPU VM; they are not independent hardware replications. All source/model/backend/runner/protocol hashes and raw observations are retained.
Every complete arm additionally records CPU steal. Aggregate steal must be <=5% and every sampled interval <=10%; unavailable/reset counters disqualify eligibility. A failed host gate invalidates qualification without dropping or selectively rerunning traces. These are prospective conditions; no earlier unmonitored result is retroactively labeled clean.

This is a restricted synthetic burst-serving comparison for Qwen2.5 0.5B FP16, under the fixed worker cap and finite native tuning sweep. The timing pattern is deliberately a burst where short work follows expensive prefills. It establishes neither typical production prevalence nor general superiority over inference engines or peer-size model quality. Conventional admission delay/cost ordering can also be implemented outside Lattice; native execution kernels and batching belong to llama.cpp. Defaults remain unchanged, accelerator support is untested, and Lattice remains an unreleased development build.
Chat framing aligns instruction requests with the model's intended interface; it is not a demonstrated fix for native batching-related numerical divergence. Any output-preservation pass applies only to the recorded finite prompts and configurations, not arbitrary future prompts.

See [failed original confirmation](burst_admission_confirmation.md), [boundary regressions](admission_boundaries.md) and [competitive plan](competitive_execution_plan.md). Boundary results used the earlier raw framing and must not be described as chat-framed confirmation evidence.

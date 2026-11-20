# Direct llama.cpp versus Lattice two-slot serving

Both arms run the same pinned two-slot llama.cpp worker, model, context, threads and server configuration. The direct arm submits concurrent completion streams directly to the native HTTP endpoint. The Lattice arm uses its request Runtime on the same backend path. The test isolates Lattice request/admission/streaming overhead; it is not a different-engine comparison.

Each pair starts a 128-token-capped long generation, waits for its first nonempty text chunk, waits 20 ms, and submits an 8-token-capped short request. Both workers remain resident, but only one arm executes at a time. Trial arm order is seeded and randomized.

| Block | Arm | Trials | Short P50 ms | Long P50 ms | Pair makespan P50 ms | Short finished before long | Greedy mismatches | Median sampled RSS MiB |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| direct-lattice-batching-headtohead-20261120 | direct_llama_cpp | 10 | 243.6 | 398.0 | 398.2 | 8/10 | 0 | 1328 |
| direct-lattice-batching-headtohead-20261120 | lattice_runtime | 10 | 281.6 | 417.8 | 418.4 | 7/10 | 0 | 1329 |
| direct-lattice-batching-headtohead-session2-20261120 | direct_llama_cpp | 10 | 222.7 | 343.7 | 350.8 | 5/10 | 0 | 1328 |
| direct-lattice-batching-headtohead-session2-20261120 | lattice_runtime | 10 | 248.1 | 367.0 | 373.6 | 4/10 | 0 | 1332 |

Only measured total latency, makespan, output tokens and sampled RSS are compared here. Native queue time is unavailable. Historical direct summary TTFT/queue fields are invalid placeholders and must not be used; metric-errata.json preserves that correction. Real direct TTFT was captured only in the second block raw short.client_ttft_ms.

This comparison cannot establish a unique Lattice batching advantage because both arms use the same upstream continuous-batching engine. The one-slot/two-slot product comparison against standard serial service is in [benchmark_followup_results.md](benchmark_followup_results.md).

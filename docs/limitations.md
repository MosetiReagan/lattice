# Current limitations

This is a Phase B CPU baseline, not the adaptive inference engine promised for Lattice 1.0. There is one real backend adapter and one tested FP16 model. No speculative algorithm, KV optimization policy, quantized variant selection, model routing, cost estimator, adaptive controller or learned policy is implemented. Native within-request KV and CPU kernels belong to llama.cpp. Cache reuse and speculation are disabled to preserve the standard baseline.

The queue allows concurrent clients but executes one request at a time. Cancellation reloads the worker; long requests can delay queued work until its deadline. No fairness beyond asyncio lock ordering, continuous batching, per-tenant quotas, hot model swapping or crash recovery certification. CLI benchmark/profile/optimize/compare workflows and a benchmark API job system remain planned. The benchmark endpoint explicitly returns 501. Public schema supports only the documented subset of chat/text controls and refuses the rest.

No frozen workload baseline, held-out quality suite, reproducible performance improvement, memory saving or energy measurement exists. A factual answer in a smoke test does not establish quality preservation. All unsupported hardware is untested. See benchmark_results.md for release gate status, security.md for security limitations, and roadmap.md for planned next work.

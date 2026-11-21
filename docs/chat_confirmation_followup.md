# Frozen chat confirmation: failure and next controlled experiment

The thirty paired traces and all three sessions completed. This study remains **failed**, not a competitor win. Both native development leaders were retained as frozen challengers.

- Quality/errors passed: all360 corresponding responses per arm had identical token IDs, text and prompt lengths; no request failed. Absolute strict copy-task correctness was355/360 in each arm.
- Interactive P95 was2,971ms versus29,880ms for the native latency leader and37,826ms for the native throughput leader.
- Against the throughput leader, aggregate throughput ratio was0.9532, with clustered95% interval[0.9416,0.9634]. Session three's ratio was0.9425. Both miss the frozen>=0.95 requirements.
- One native1 arm exceeded the unchanged10% CPU-steal interval limit (14.62%). The whole study therefore also failed resource eligibility; no trace was excluded or selectively repeated.
- Boundary diagnostics retained negative cases: interactive-only throughput was9.09 versus12.90tokens/s, and bulk-only throughput was0.401 versus0.406tokens/s. The policy remains opt-in.

## Measured configuration difference

The native throughput leader reported10,585 reused prompt tokens out of238,776 total prompt-token positions across the study, about4.43%. Its request payload enabled native prefix reuse. Lattice's concurrent payload explicitly forced `cache_prompt=False`; it recomputed these prefixes. This is a concrete configuration difference and a plausible throughput cost, not yet a causally isolated attribution of the complete gap.

Next, extend the existing identity/token-checked logical prefix eligibility to separate native slot leases. Keep the current default disabled. Require explicit cached mode and operator opt-in, account for the complete fixed native KV pool under the configured cache budget, and invalidate on incompatible/private-standard execution, cancellation, restart and failed generation. Never share eligibility between slots or across model/tokenizer/context identities. Upstream llama.cpp remains the physical KV allocator/verifier.

Measure cached versus uncached concurrent execution independently on development prompts, under identical resource controls, before integrating the successful component into a newly frozen protocol with fresh held-out seeds. Keep the failed study, thresholds, sample budget and every regression intact. The previous quality failure and this throughput/resource failure are not repaired by a later protocol.

A separate controlled CPU-bandwidth allocation may be evaluated for both native and Lattice arms to leave headroom on the shared host. Resource and performance thresholds remain unchanged; do not relabel contested measurements as clean.

# Adaptive cache versus direct native cache

Thirty three-arm trials compare direct uncached requests, direct llama.cpp native caching and Lattice adaptive execution on identical raw prompts. These are the exact public prompts covered by the existing measured policy; templates and tokenization are matched, and the adaptive arm selected cached execution on every measured request. Both workers have matching model/backend/context/thread/memory settings.

| Arm | Requests | P50 ms | P95 ms | Median native cached tokens | Selected execution |
|---|---:|---:|---:|---:|---|
| direct_uncached | 30 | 928.3 | 968.3 | 0 | {"direct_uncached": 30} |
| direct_native_cache | 30 | 218.1 | 263.7 | 563 | {"direct_native_cache": 30} |
| lattice_adaptive | 30 | 230.9 | 254.9 | 563 | {"cached": 30} |

All 30 triples matched exact greedy token IDs and text, with identical prompt-token lengths. Native caching and Lattice both reduce time versus uncached execution; the direct native-cache arm is the relevant baseline for unique value. This run does not demonstrate a 20% Lattice advantage over native caching.

The direct cache-on and cache-off arms share native state; this is a mixed cache-on/cache-off trace. Only four exact prompt variants are repeated. Do not infer general held-out equivalence or broad cache performance. Earlier chat/raw framing mismatches are preserved in separate excluded pilot folders; their latency/output differences are not evidence of an optimization.

Raw requests, token IDs, policy decisions, native timing/cached-token counters and hashes are retained alongside the validated summary. The broader decision and next gates are in [competitive_execution_plan.md](competitive_execution_plan.md).

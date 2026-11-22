# Lattice release readiness

The local CPU build remains at 0.3.0.dev0. The 1.0 decision follows the original ten release gates.

| Gate | Evidence and status |
|---|---|
| G1 Functional runtime | Real Qwen generation through CLI and streaming HTTP on CPU. |
| G2 Backend compatibility | Pinned llama.cpp CPU backend tested with registered Qwen artifacts. |
| G3 Reproducible baseline | Frozen source, model checksums, workload parameters and repeated standard CPU observations are available. |
| G4 Independent optimizations | Native greedy speculation, prefix reuse and quantized execution were tested separately. |
| G5 Adaptive execution | Demonstrated for the measured prefix workload. Model and precision substitution still lack qualification. |
| G6 Quality preservation | Measured on frozen prompts and corpus tests. Q4 exceeds the configured perplexity tolerance, and broader policy quality remains open. |
| G7 Performance evidence | Repeatable warmed-prefix benefit and a separately frozen cache-budgeted chat burst study that passed its restricted latency/throughput/output/resource gates. General workload and independent hardware evidence remain open. |
| G8 Stability | Real CPU tests cover cancellation, timeouts, concurrency and worker recovery for the tested configuration. |
| G9 Documentation | Architecture, compatibility, experimental methods and limitations are documented. |
| G10 Reproducibility | Local reruns and artifact checks are available. Independent reproduction remains unverified. |

The 1.0 acceptance decision remains open because broad adaptive quality and independent reproduction lack evidence. This checkout has no configured Git remote or publication destination.

The later [held-out CPU burst confirmation](burst_admission_confirmation.md) did not qualify a competitor win: performance gates passed against the frozen native baseline, but exact greedy output preservation failed. Strict task correctness was also zero with raw prompt framing. The policy remains experimental and opt-in; G7's existing warmed-prefix evidence must not be recast as superiority over native prefix caching. Boundary regressions and failures remain [visible](admission_boundaries.md).

Subsequent chat-framed development included a cache-budgeted held-out run that passed all frozen gates for one restricted synthetic burst configuration. The [v7 report](chat-cache-budget-confirmation-v7.md) records matching outputs and performance gates against both native challengers, plus the host and cache-path checks. Earlier cache-budgeted runs failed CPU eligibility and remain preserved. The current suite passes 171 tests, including real CPU integration; this does not remove the broader quality and independent-reproduction gaps or [scope limitations](benchmark_environment_concern.md). No release gate is lowered.

Pinned one-thread development remains exploratory: all tested outputs matched, but four of eleven tuning arms exceeded the prospective per-interval CPU-steal limit. The later cache-budgeted v7 confirmation separately passed its restricted frozen gates against both native challengers; see its [report](chat-cache-budget-confirmation-v7.md). That task-specific result does not establish broad engine superiority or close the independent-reproduction and quality gaps required for 1.0.

See [benchmarks](benchmark_results.md), [quality](quality_preservation.md) and [multilingual evaluation](multilingual_datasets.md).

# Direct llama.cpp versus Lattice runtime

This paired test uses the same pinned llama.cpp binary, libraries, FP16 Qwen2.5 0.5B artifact, one-slot worker settings, chat template, tokenizer, token-ID completion request and deterministic sampler on both arms. The direct arm sends requests to the native completion endpoint; the Lattice arm uses the Runtime request/admission/metrics path. It measures control-plane overhead, not superiority over another inference engine.

The second session reran all five workloads with explicit per-workload matching of worker address-space caps and a different arm-order seed. An earlier exploratory run with an incorrect memory-cap protocol is preserved in the initial-cap-mismatch archive and excluded entirely; both reported sessions match caps on all five workloads. Across all included pairs, prompt and output token IDs match exactly.

| Workload | Valid pairs | Direct P50 ms | Lattice P50 ms | Lattice P50 change | Direct / Lattice tokens/s |
|---|---:|---:|---:|---:|---:|
| short | 20 | 270.2 | 265.9 | -1.6% | 50.96 / 51.64 |
| long_prompt | 20 | 1591.5 | 1603.9 | +0.8% | 9.44 / 9.37 |
| long_response | 20 | 263.6 | 273.1 | +3.6% | 50.49 / 48.38 |
| repeated_prefix | 20 | 1016.6 | 1018.5 | +0.2% | 15.88 / 15.81 |
| memory_constrained | 20 | 421.4 | 427.4 | +1.4% | 33.33 / 32.95 |

Latency difference is (Lattice P50 / direct P50 - 1); positive means Lattice is slower. Throughput is observed generated tokens divided by summed per-request wall time, not system-wide sustainable throughput. Worker RSS is sampled process memory, not total host memory.

These results do not support a claim that Lattice beats llama.cpp. They show near parity in direct single-slot execution on this tested model and CPU. The possible product advantage is the tested two-slot mixed-request path, which runs through the same upstream engine; that is useful product integration, not a new Lattice kernel.

Both sessions' raw prompts, outputs, token IDs, caps, artifact hashes and manifests are retained under their result directories. The initial memory-cap mismatch archive is separate and excluded for that workload.

# Controlled comparison frame

One workload: 1,009 input tokens, at most 16 output tokens, CPU threads 4, context 2,048. Precision changes representation from the same FP16 source; warm rows exclude identical priming work in both arms. Different sessions and exclusions limit direct causal comparisons; the paired cache table in benchmark_results.md is the stronger same-weight latency comparison.

| Configuration | Observations | Median latency (ms) | Generated tokens / request-second | Median sampled worker RSS (MiB) | Quality evidence |
|---|---:|---:|---:|---:|---|
| Standard FP16 | 30 | 1550.37 | 10.29 | 1313.9 | PPL 21.8762; smoke 11/22 |
| Explicit Q8_0 | 30 | 1822.61 | 8.70 | 750.7 | PPL 22.0205; smoke 11/22 |
| Explicit Q4_K_M | 30 | 2031.46 | 7.89 | 606.3 | PPL 22.7338; smoke 10/22 |
| Warm FP16 prefix reuse | 90 | 232.77 | 67.64 | 1314.0 | 0/90 greedy mismatches; optimized-path PPL not measured |
| Warm adaptive FP16 | 30 | 217.55 | 72.95 | Unavailable | 0/30 greedy mismatches; known prompts only |

Speculation is measured separately against the identical 1.5B Q8 target and must not be compared to these 0.5B values as if the target were unchanged. Sampled RSS is not exact peak allocation; no energy result is available. Smaller quantized files and lower RSS did not imply lower long-prompt latency on this CPU. Q4 is quality-rejected and Q8 automatic substitution remains unqualified.

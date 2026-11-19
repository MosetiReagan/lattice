# Quantized execution and measured quality

Implemented: CPU GGUF FP16/Q8_0/Q4_K_M execution through llama.cpp, exact-artifact verification, local Q8/Q4 conversion from the frozen FP16 source, tokenizer fingerprint checks, an explicit capability matrix and quality-qualification rules. Native low-bit kernels and the converter are upstream functionality. GPTQ, AWQ, bitsandbytes, BF16/FP32 and other accelerators have no tested Lattice adapter here; matching a bit width does not make layouts interchangeable.

`precision-session-1` randomizes representation block order and compares the same original 0.5B model source at the same tokenizer/context/greedy settings. Each representation has 30 observations for short and long-prompt workloads, three warmups per workload, sampled worker RSS, native prefill/decode timings, artifact byte counts, load observations, 22 public smoke tasks and WikiText-2 raw test perplexity over 32 chunks of 256 tokens. Native perplexity scores the final half of each chunk; this is a subset, not the full WikiText corpus. Native uncertainty is retained and is not a confidence interval for the ratio of two representations.

| Representation | Measured artifact bytes | WikiText subset PPL | Change vs FP16 | Strict smoke tasks |
|---|---:|---:|---:|---:|
| FP16 GGUF | 1,266,425,696 | 21.8762 | baseline | 11/22 |
| Q8_0 | 675,710,816 | 22.0205 | +0.66% | 11/22 |
| Q4_K_M | 491,400,032 | 22.7338 | +3.92% | 10/22 |

Q4 exceeds the proposed 2% perplexity tolerance and loses one smoke task; it is rejected for automatic selection. Q8's point estimate is inside the PPL tolerance, but 22 public tasks cannot establish <=1 percentage-point held-out noninferiority, so automatic Q8 substitution also remains unqualified. Explicit operator/user model selection is supported without presenting it as quality-preserving adaptation. Smaller files are measured storage savings, not measured peak-memory savings; consult sampled RSS records separately.

Reproduce conversions with `uv run --no-sync python scripts/quantize_cpu.py Q8_0` and `... Q4_K_M` in a fresh provisioned workspace. These commands refuse overwrites and preserve baseline weights. `experiments/precision_cpu.py` runs the comparison after `scripts/prepare_wikitext.py`. Conversion manifests record source/candidate hashes, native tool hash, backend commit and unchanged tokenizer fingerprint. Published values above are this one CPU-session subset study, not universal quantization quality results.

The separate expanded [dataset-intake study](dataset_results.md) evaluates all 1,167 full WikiText-2 test chunks under the same native half-window protocol: FP16 PPL 17.4152, Q8_0 17.5250 (+0.63%), Q4_K_M 18.0919 (+3.89%). This preserves the earlier subset results and confirms that Q4 still exceeds the proposed 2% point-estimate tolerance. Native uncertainty is not a ratio confidence interval; automatic Q8 qualification remains unavailable.

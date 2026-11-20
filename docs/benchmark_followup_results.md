# Fresh CPU precision benchmark

Two sequential benchmark blocks compare the frozen Qwen2.5 0.5B F16, Q8_0 and Q4_K_M artifacts from the same source checkpoint on the pinned llama.cpp CPU backend. Each block has ten measured trials and two warmups per workload. Prompt inputs, output caps, context, thread count, sampler settings and runtime code are controlled; precision is the treatment factor. This is a single shared VM study with small samples, not a production SLA or formal significance test. A brief accidental overlap occurred during the final Q4 quality phase of block 1; all Q4 block-1 latency, throughput, memory and quality values are explicitly excluded. The raw observations and interruption record are retained.

Each table cell reports block 1 / block 2. Latency is median total request time in milliseconds; throughput is aggregate observed generated tokens per second over the block makespan.

| Model | Workload | P50 latency ms, block 1 / 2 | P95 latency ms, block 1 / 2 | Tokens/s, block 1 / 2 | Completed / attempted per block |
|---|---|---:|---:|---:|---:|
| qwen2.5-0.5b-instruct-f16 | short | 385.4 / 291.4 | 417.3 / 322.1 | 40.75 / 56.18 | 10/10 / 10/10 |
| qwen2.5-0.5b-instruct-f16 | long_prompt | 1605.0 / 1518.1 | 1674.6 / 1551.2 | 9.93 / 10.53 | 10/10 / 10/10 |
| qwen2.5-0.5b-instruct-f16 | short_response | 245.3 / 252.8 | 254.1 / 264.9 | 16.42 / 15.70 | 10/10 / 10/10 |
| qwen2.5-0.5b-instruct-f16 | long_response | 1779.6 / 1660.0 | 1815.1 / 2070.1 | 71.84 / 73.23 | 10/10 / 10/10 |
| qwen2.5-0.5b-instruct-f16 | repeated_prefix | 946.8 / 992.7 | 970.0 / 1037.9 | 16.91 / 16.11 | 10/10 / 10/10 |
| qwen2.5-0.5b-instruct-f16 | concurrent | 1045.6 / 1053.2 | 2062.1 / 2113.5 | 61.84 / 60.31 | 10/10 / 10/10 |
| qwen2.5-0.5b-instruct-f16 | mixed | 1315.0 / 1064.2 | 4562.7 / 4039.0 | 30.81 / 35.65 | 10/10 / 10/10 |
| qwen2.5-0.5b-instruct-f16 | memory_constrained | 426.3 / 422.2 | 485.9 / 438.2 | 36.55 / 38.64 | 10/10 / 10/10 |
| qwen2.5-0.5b-instruct-q8_0 | short | 224.1 / 228.9 | 271.5 / 245.8 | 68.39 / 69.07 | 10/10 / 10/10 |
| qwen2.5-0.5b-instruct-q8_0 | long_prompt | 1739.2 / 1688.7 | 1803.9 / 1778.7 | 9.22 / 9.38 | 10/10 / 10/10 |
| qwen2.5-0.5b-instruct-q8_0 | short_response | 272.1 / 265.7 | 303.5 / 281.8 | 14.47 / 14.95 | 10/10 / 10/10 |
| qwen2.5-0.5b-instruct-q8_0 | long_response | 1464.4 / 1241.5 | 1509.4 / 1288.2 | 89.85 / 102.73 | 10/10 / 10/10 |
| qwen2.5-0.5b-instruct-q8_0 | repeated_prefix | 1075.3 / 1028.9 | 1131.5 / 1085.4 | 14.80 / 15.39 | 10/10 / 10/10 |
| qwen2.5-0.5b-instruct-q8_0 | concurrent | 931.1 / 916.7 | 1861.4 / 1864.0 | 69.66 / 69.83 | 10/10 / 10/10 |
| qwen2.5-0.5b-instruct-q8_0 | mixed | 958.4 / 889.6 | 4081.7 / 3901.9 | 35.05 / 37.01 | 10/10 / 10/10 |
| qwen2.5-0.5b-instruct-q8_0 | memory_constrained | 393.7 / 376.1 | 444.3 / 392.7 | 39.91 / 42.61 | 10/10 / 10/10 |
| qwen2.5-0.5b-instruct-q4_k_m | short | excluded / 217.4 | excluded / 229.3 | excluded / 72.97 | excluded / 10/10 |
| qwen2.5-0.5b-instruct-q4_k_m | long_prompt | excluded / 1836.6 | excluded / 1878.0 | excluded / 8.68 | excluded / 10/10 |
| qwen2.5-0.5b-instruct-q4_k_m | short_response | excluded / 286.1 | excluded / 327.8 | excluded / 13.65 | excluded / 10/10 |
| qwen2.5-0.5b-instruct-q4_k_m | long_response | excluded / 1235.3 | excluded / 1320.1 | excluded / 103.64 | excluded / 10/10 |
| qwen2.5-0.5b-instruct-q4_k_m | repeated_prefix | excluded / 1108.1 | excluded / 1124.5 | excluded / 14.45 | excluded / 10/10 |
| qwen2.5-0.5b-instruct-q4_k_m | concurrent | excluded / 879.8 | excluded / 1728.0 | excluded / 74.38 | excluded / 10/10 |
| qwen2.5-0.5b-instruct-q4_k_m | mixed | excluded / 990.9 | excluded / 4456.7 | excluded / 32.68 | excluded / 10/10 |
| qwen2.5-0.5b-instruct-q4_k_m | memory_constrained | excluded / 389.5 | excluded / 402.2 | excluded / 41.09 | excluded / 10/10 |

The memory-constrained workload preserves admission failures rather than treating them as zero latency. Worker RSS is sampled process memory, not total physical memory. Workloads named concurrent and mixed used one native slot and therefore measure queued single-slot behavior, not continuous batching.

## Storage and smoke quality

| Precision | Artifact bytes | Strict smoke block 1 | Strict smoke block 2 |
|---|---:|---:|---:|
| qwen2.5-0.5b-instruct-f16 | 1,266,425,696 | 11/22 | 11/22 |
| qwen2.5-0.5b-instruct-q8_0 | 675,710,816 | 11/22 | 11/22 |
| qwen2.5-0.5b-instruct-q4_k_m | 491,400,032 | excluded | 10/22 |

Smoke scoring is strict output-format scoring on the original 22 self-authored cases; it is not held-out quality evidence. The frozen 600-case-per-precision study remains separate and controls substitution decisions.

## Artifact size and sampled worker RSS

Artifact size is exact file storage. Sampled worker RSS is the median 10 ms sampler peak, not total host memory.

| Model | Artifact bytes | File-size change vs FP16 | Short-workload RSS MiB, block 1 / 2 | Memory-constrained RSS MiB, block 1 / 2 |
|---|---:|---:|---:|---:|
| qwen2.5-0.5b-instruct-f16 | 1,266,425,696 | +0.0% | 1298 / 1298 | 1305 / 1305 |
| qwen2.5-0.5b-instruct-q8_0 | 675,710,816 | -46.6% | 735 / 735 | 742 / 742 |
| qwen2.5-0.5b-instruct-q4_k_m | 491,400,032 | -61.2% | excluded / 589 | excluded / 597 |

File size reduction is not a claim of total-memory savings. RSS includes runtime libraries, mappings and context allocations; this VM has no isolated hardware memory counter.

## Reproduction and raw records

Workload file: ../workloads/cpu-v2-followup.json. Exact model, backend, code, platform and workload hashes are retained per run. Raw JSONL preserves every measured request, token IDs, outputs, queue timing, observed prompt/output lengths, sampled RSS and failures. Both precision blocks, the interrupted overlap attempt, and the paired batching run are retained under benchmark-followup-20261120, benchmark-followup-20261120-session2, benchmark-followup-20261120-session2-interrupted, and benchmark-followup-batching-20261120. The erroneous overlap and its exclusion are explicitly recorded.

Run lattice benchmark --model MODEL --workload-file benchmarks/workloads/cpu-v2-followup.json --trials 10 --warmups 2 --quality --output NEW_DIRECTORY for another block. Use a fresh directory.

## Paired one-slot versus two-slot serving

This separate test used the same FP16 model and paired short/long requests. The short request arrived 20 ms after the long request's first text chunk. Ten trials per arm were run with both workers resident, alternating arm order. Greedy token IDs matched for every request.

| Native slots | Short-request P50 ms | Short TTFT P50 ms | Short queue P50 ms | Long-request P50 ms | Pair makespan P50 ms | Short finished before long | Tokens/s | Median sampled worker RSS |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1462.7 | 1389.0 | 1352.115 | 1426.6 | 1537.9 | 0/10 | 86.26 | 1306 MiB |
| 2 | 200.8 | 65.9 | 0.055 | 1541.8 | 1542.2 | 10/10 | 86.82 | 1332 MiB |

In this workload, two slots reduced short-request P50 by 86.3% and median queue wait from 1352.115 ms to 0.055 ms. Long-request P50 changed by +8.1%, pair makespan by +0.3%, and aggregate throughput by +0.6%. This is a narrow 10-pair CPU result, not general production evidence. Both arms passed the same 11/22 strict smoke tasks, with no greedy mismatches or sampled worker swap.

## Quality context

The full frozen task evaluation and WikiText corpus benchmark are in [dataset_results.md](dataset_results.md): 1,728 scored model-case outputs and 72 explicit context skips; full-corpus PPL 17.4152 FP16, 17.5250 Q8_0 (+0.63%), and 18.0919 Q4_K_M (+3.89%). Q4 exceeds the existing proposed 2% PPL tolerance. Q8 remains unqualified for automatic substitution. These fresh performance observations do not relax those quality gates.

No automatic model or precision policy is qualified by this run.

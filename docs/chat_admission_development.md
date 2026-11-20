# Chat-framed admission development sweep

Two development trace seeds (9001/9002), 24 requests per arm; no confidence or confirmation claim. Source instructions are rendered with the model's actual chat template before timing. Every arm receives identical rendered prompts, greedy sampling, caps and arrivals. All tested arms and regressions are retained.

| Arm | Interactive P95 ms | Bulk P95 ms | Tokens/s | Exact task correct | Output mismatches | Errors |
|---|---:|---:|---:|---:|---:|---:|
| lattice_coalesce2 | 846.4 | 11345.3 | 3.033 | 22/24 | 0 | 0 |
| lattice_coalesce4 | 1366.2 | 11405.1 | 3.018 | 22/24 | 0 | 0 |
| lattice_coalesce3 | 1450.5 | 11667.9 | 2.954 | 22/24 | 0 | 0 |
| lattice_coalesce8 | 6766.3 | 11285.7 | 3.056 | 22/24 | 0 | 0 |
| simple_cost4 | 7911.6 | 11046.0 | 3.122 | 22/24 | 0 | 0 |
| native4 | 10544.4 | 10931.2 | 3.153 | 22/24 | 0 | 0 |
| native16_b1024 | 10701.0 | 10678.6 | 3.297 | 22/24 | 0 | 0 |
| native16 | 10818.3 | 10619.3 | 3.222 | 22/24 | 0 | 0 |
| native8 | 11048.3 | 11085.6 | 3.109 | 22/24 | 0 | 0 |
| native3 | 11126.4 | 11038.7 | 3.116 | 22/24 | 0 | 0 |
| native2 | 11216.9 | 10766.2 | 3.103 | 22/24 | 0 | 0 |
| native1 | 11306.7 | 10700.7 | 3.093 | 22/24 | 0 | 0 |
| native8_b512 | 11323.0 | 11433.9 | 3.026 | 22/24 | 0 | 0 |
| native16_b512 | 11540.9 | 11127.2 | 3.079 | 22/24 | 0 | 0 |
| native8_b1024 | 11567.5 | 11603.9 | 3.045 | 22/24 | 0 | 0 |
| native8_b128 | 11658.0 | 11680.9 | 2.950 | 22/24 | 0 | 0 |
| native16_b128 | 11950.8 | 11256.5 | 2.999 | 22/24 | 0 | 0 |
| native16_b64 | 12308.3 | 11720.3 | 2.819 | 22/24 | 0 | 0 |
| native8_b64 | 12398.6 | 12412.7 | 2.775 | 22/24 | 0 | 0 |

Provisional lowest native interactive P95 in the two completed development blocks: **native4**. Provisional candidate passing development output/error/throughput conditions: **lattice_coalesce8**. Native slots 1/2/3/4/8/16 were tested; eight- and sixteen-slot logical batches 64/128/256/512/1024 were tested, with microbatch min(256,batch). This is not a final confirmation selection or global optimum claim.

After the first sweep, native4 had the lowest pooled native P95, so focused tuning started for native4 batches 64/128/512/1024, two/eight-slot coalescing batches 512/1024 and matching thin queues. It was interrupted after sustained 74-75% CPU steal was observed. Its completed observations remain below; no winner is selected from the incomplete block. This environmental concern was discovered after measurements began, so earlier development blocks also lack a certified clean-CPU history. None is confirmatory evidence. The original raw-completion confirmation remains failed.

## Interrupted focused diagnostics

| Trace | Arm | Recorded requests | Interactive P95 ms | Actual tokens/s | Errors |
|---|---|---:|---:|---:|---:|
| 0 | native4_b1024 | 12 | 11079.6 | 3.147 | 0 |
| 0 | native4_b128 | 12 | 9513.5 | 2.922 | 0 |
| 0 | lattice_coalesce2_b1024 | 12 | 1664.9 | 3.108 | 0 |
| 0 | lattice_coalesce8_b512 | 12 | 11282.4 | 3.027 | 0 |
| 0 | native4_b512 | 12 | 11294.8 | 3.087 | 0 |
| 0 | lattice_coalesce8_b1024 | 12 | 6044.0 | 3.012 | 0 |
| 0 | simple_cost8 | 12 | 10040.3 | 3.056 | 0 |
| 0 | simple_cost2 | 12 | 4059.1 | 3.170 | 0 |
| 0 | lattice_coalesce2_b512 | 12 | 618.7 | 3.041 | 0 |
| 0 | native4_b64 | 12 | 8686.0 | 2.733 | 0 |
| 1 | native4_b1024 | 12 | 26711.5 | 1.269 | 0 |
| 1 | native4_b128 | 12 | 44975.5 | 0.584 | 0 |
| 1 | lattice_coalesce8_b512 | 12 | 28374.4 | 0.628 | 0 |

No unfinished arm is filled with estimated numbers or counted as a success. Resume with a separately named development block after CPU eligibility is restored. New confirmation must retain the original 20% latency / 5% throughput targets, exact-output checks, fixed sample budget and per-arm CPU-steal eligibility; do not rerun or relabel the failed raw study.

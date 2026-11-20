# Held-out burst admission confirmation

This experiment tests opt-in four-slot Lattice admission with a 50 ms grace for default-priority requests exceeding 1,024 input bytes or 32 output tokens. Higher-priority requests bypass the grace. Latency includes grace, queueing and generation. The default priority/FIFO serving policy is unchanged.

Development compared native 1/2/3/4/8 slots and native8 batch sizes 64/128/256/512/1024. Native8 with batch256 was frozen as the strongest interactive-P95 native development baseline. A thin four-slot cost-priority baseline outside Lattice is also reported. This is a finite tuning sweep, not a globally optimal competitor claim.

## Frozen confirmation

Three sessions each contain ten untouched trace seeds. Each trace has six diverse long-input copy tasks followed by six short-input copy tasks at fixed, exogenous arrival times. Both arms use the same Qwen2.5 0.5B FP16 artifact, pinned native binary, four CPU threads, per-request 2k context and 4 GiB worker address-space limit. Actual EOS/output lengths are retained; no generation is forced to hit its cap.

| Baseline | Interactive P95 ms | Candidate P95 ms | P95 ratio [95% interval] | Throughput baseline / candidate tokens/s | Throughput ratio [95% interval] |
|---|---:|---:|---|---|---|
| native8 | 12125.3 | 4843.5 | 0.399 [0.102, 0.540] | 9.64 / 10.73 | 1.114 [0.964, 1.505] |
| simple_cost4 | 10434.6 | 4843.5 | 0.464 [0.327, 0.648] | 11.01 / 10.73 | 0.975 [0.927, 1.004] |

## Gate decision

Restricted gate pass: **False**. Individual frozen gates: `{"latency": true, "quality_and_errors": false, "throughput": true, "worker_cap_and_no_swap": true}`.

Raw results contain 3 token/text/prompt-length mismatches and 0 failed requests across 30 paired traces. Exact-match equality establishes only this finite tested scope. Numerical task correctness is separate from baseline-output preservation.

Absolute copy-task exact correctness (stripped output must equal the requested value): native8: 0/360; simple_cost4: 0/360; lattice_coalesce4: 0/360. Identical incorrect answers are not evidence of good task quality.

The latency target requires at least 20% interactive P95 improvement and the throughput target permits at most 5% loss. Both must hold in every session and for the predeclared clustered confidence bounds. If a gate fails or remains inconclusive, these measurements do not qualify the claim. Gates were not relaxed.

| Session | Native interactive P95 ms | Candidate P95 ms | P95 ratio | Throughput ratio | Native / candidate bulk P95 ms |
|---|---:|---:|---:|---:|---|
| 1 | 11676.7 | 3409.3 | 0.292 | 0.971 | 11837.5 / 12089.6 |
| 2 | 11960.5 | 5537.5 | 0.463 | 0.988 | 12328.4 / 12464.8 |
| 3 | 19854.7 | 6566.3 | 0.331 | 1.364 | 66352.5 / 15417.6 |

## Resources and interpretation

Worker and control-plane RSS are sampled separately; the worker hard limit is address space, not RSS. Control-plane RSS is the common benchmark harness process, not an isolated production gateway measurement. All raw dispatch lateness, EOS, request timings and failures are preserved in the result files. The confirmation contains only one burst family on one shared CPU VM; it does not certify GPU support, model-quality improvements, production prevalence or all workloads. Long-only and interactive-only traffic can respond differently to the opt-in delay. A separately configured admission shim can implement the same conventional heuristic; no exclusivity or new-kernel claim follows.

The confidence intervals use 10,000 fixed-seed hierarchical paired bootstrap replicates, resampling sessions and whole traces. Three sessions on one VM are not independent hardware replications. The frozen protocol and source hashes are retained in the result directory. See [the competitive execution plan](competitive_execution_plan.md).

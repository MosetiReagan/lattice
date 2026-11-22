# Chat-framed admission boundaries

These five single-trace diagnostics were fixed before confirmation. They do not determine tuning or replace any primary gate. Both arms use actual model chat framing, identical source inputs/arrivals, greedy sampling, caps and worker resource limits. Empty traffic classes have unavailable P95. There are no confidence intervals from these single traces.

| Case | Arm | Interactive P95 ms | Bulk P95 ms | Tokens/s | Errors | Exact task correct | Worker MiB |
|---|---|---:|---:|---:|---:|---:|---:|
| interactive_only | native4_b64_noram | 3084.2 | Unavailable | 10.571 | 0 | 12/12 | 1378.9 |
| interactive_only | lattice_coalesce2_cached | 2787.4 | Unavailable | 11.267 | 0 | 12/12 | 1326.1 |
| bulk_only | native4_b64_noram | Unavailable | 38719.2 | 0.421 | 0 | 5/6 | 1379.5 |
| bulk_only | lattice_coalesce2_cached | Unavailable | 40197.2 | 0.423 | 0 | 5/6 | 1339.5 |
| mixed_25_percent_interactive | native4_b64_noram | 52277.8 | 62051.7 | 0.572 | 0 | 12/12 | 1380.5 |
| mixed_25_percent_interactive | lattice_coalesce2_cached | 3251.9 | 64772.3 | 0.571 | 0 | 12/12 | 1339.5 |
| mixed_75_percent_interactive | native4_b64_noram | 12850.1 | 25735.2 | 1.327 | 0 | 12/12 | 1379.5 |
| mixed_75_percent_interactive | lattice_coalesce2_cached | 3767.3 | 21955.2 | 1.547 | 0 | 12/12 | 1339.0 |
| interactive_arrives_late | native4_b64_noram | 28639.2 | 41361.9 | 0.771 | 0 | 12/12 | 1380.0 |
| interactive_arrives_late | lattice_coalesce2_cached | 15538.3 | 40754.1 | 0.784 | 0 | 12/12 | 1339.1 |

All results, including regressions, failures and nonidentical outputs, are retained in the raw JSONL and analysis.json. One favorable trace is not a workload-level performance claim. Sampled worker RSS is not allocator peak; the hard worker cap is address space. Control-plane RSS is the common benchmark harness, not isolated production gateway memory.

See [primary confirmation](chat_admission_confirmation.md). The candidate is opt-in and a conventional admission heuristic, not a new kernel or stronger language model.

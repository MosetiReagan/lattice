# Chat-framed admission boundaries

These five single-trace diagnostics were fixed before confirmation. They do not determine tuning or replace any primary gate. Both arms use actual model chat framing, identical source inputs/arrivals, greedy sampling, caps and worker resource limits. Empty traffic classes have unavailable P95. There are no confidence intervals from these single traces.

| Case | Arm | Interactive P95 ms | Bulk P95 ms | Tokens/s | Errors | Exact task correct | Worker MiB |
|---|---|---:|---:|---:|---:|---:|---:|
| interactive_only | native4_b64_noram | 3090.1 | Unavailable | 11.515 | 0 | 12/12 | 1379.0 |
| interactive_only | lattice_coalesce2_cached | 2984.8 | Unavailable | 11.974 | 0 | 12/12 | 1326.1 |
| bulk_only | native4_b64_noram | Unavailable | 39625.2 | 0.437 | 0 | 6/6 | 1379.5 |
| bulk_only | lattice_coalesce2_cached | Unavailable | 39673.0 | 0.453 | 0 | 6/6 | 1339.5 |
| mixed_25_percent_interactive | native4_b64_noram | 51003.4 | 61854.7 | 0.529 | 0 | 12/12 | 1380.5 |
| mixed_25_percent_interactive | lattice_coalesce2_cached | 3157.7 | 57826.1 | 0.585 | 0 | 12/12 | 1339.6 |
| mixed_75_percent_interactive | native4_b64_noram | 11949.4 | 23172.8 | 1.599 | 0 | 12/12 | 1379.6 |
| mixed_75_percent_interactive | lattice_coalesce2_cached | 3448.6 | 20071.7 | 1.838 | 0 | 12/12 | 1339.0 |
| interactive_arrives_late | native4_b64_noram | 29377.6 | 40304.5 | 0.766 | 0 | 12/12 | 1380.0 |
| interactive_arrives_late | lattice_coalesce2_cached | 16052.2 | 37094.9 | 0.842 | 0 | 12/12 | 1339.3 |

All results, including regressions, failures and nonidentical outputs, are retained in the raw JSONL and analysis.json. One favorable trace is not a workload-level performance claim. Sampled worker RSS is not allocator peak; the hard worker cap is address space. Control-plane RSS is the common benchmark harness, not isolated production gateway memory.

See [primary confirmation](chat_admission_confirmation.md). The candidate is opt-in and a conventional admission heuristic, not a new kernel or stronger language model.

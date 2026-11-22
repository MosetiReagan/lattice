# Chat-framed admission boundaries

These five single-trace diagnostics were fixed before confirmation. They do not determine tuning or replace any primary gate. Both arms use actual model chat framing, identical source inputs/arrivals, greedy sampling, caps and worker resource limits. Empty traffic classes have unavailable P95. There are no confidence intervals from these single traces.

| Case | Arm | Interactive P95 ms | Bulk P95 ms | Tokens/s | Errors | Exact task correct | Worker MiB |
|---|---|---:|---:|---:|---:|---:|---:|
| interactive_only | native4_b64_noram | 3100.4 | Unavailable | 10.495 | 0 | 12/12 | 1379.0 |
| interactive_only | lattice_coalesce2_cached | 2961.5 | Unavailable | 10.963 | 0 | 12/12 | 1326.2 |
| bulk_only | native4_b64_noram | Unavailable | 38943.0 | 0.395 | 0 | 6/6 | 1379.6 |
| bulk_only | lattice_coalesce2_cached | Unavailable | 39681.8 | 0.403 | 0 | 6/6 | 1339.1 |
| mixed_25_percent_interactive | native4_b64_noram | 51273.9 | 62166.7 | 0.524 | 0 | 12/12 | 1380.6 |
| mixed_25_percent_interactive | lattice_coalesce2_cached | 3282.1 | 61947.8 | 0.526 | 0 | 12/12 | 1339.4 |
| mixed_75_percent_interactive | native4_b64_noram | 11845.0 | 25013.2 | 1.288 | 0 | 10/12 | 1379.5 |
| mixed_75_percent_interactive | lattice_coalesce2_cached | 3828.4 | 21486.9 | 1.491 | 0 | 10/12 | 1339.0 |
| interactive_arrives_late | native4_b64_noram | 31074.7 | 43871.5 | 0.726 | 0 | 12/12 | 1380.1 |
| interactive_arrives_late | lattice_coalesce2_cached | 19006.4 | 41842.0 | 0.765 | 0 | 12/12 | 1339.1 |

All results, including regressions, failures and nonidentical outputs, are retained in the raw JSONL and analysis.json. One favorable trace is not a workload-level performance claim. Sampled worker RSS is not allocator peak; the hard worker cap is address space. Control-plane RSS is the common benchmark harness, not isolated production gateway memory.

See [primary confirmation](chat_admission_confirmation.md). The candidate is opt-in and a conventional admission heuristic, not a new kernel or stronger language model.

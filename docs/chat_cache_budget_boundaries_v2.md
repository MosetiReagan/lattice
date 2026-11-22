# Chat-framed admission boundaries

These five single-trace diagnostics were fixed before confirmation. They do not determine tuning or replace any primary gate. Both arms use actual model chat framing, identical source inputs/arrivals, greedy sampling, caps and worker resource limits. Empty traffic classes have unavailable P95. There are no confidence intervals from these single traces.

| Case | Arm | Interactive P95 ms | Bulk P95 ms | Tokens/s | Errors | Exact task correct | Worker MiB |
|---|---|---:|---:|---:|---:|---:|---:|
| interactive_only | native4_b64_noram | 3140.0 | Unavailable | 11.023 | 0 | 12/12 | 1378.9 |
| interactive_only | lattice_coalesce2_cached | 2867.5 | Unavailable | 11.605 | 0 | 12/12 | 1326.3 |
| bulk_only | native4_b64_noram | Unavailable | 38664.1 | 0.423 | 0 | 5/6 | 1379.5 |
| bulk_only | lattice_coalesce2_cached | Unavailable | 38779.8 | 0.438 | 0 | 5/6 | 1339.4 |
| mixed_25_percent_interactive | native4_b64_noram | 49286.4 | 58682.5 | 0.557 | 0 | 12/12 | 1380.6 |
| mixed_25_percent_interactive | lattice_coalesce2_cached | 3033.7 | 59169.4 | 0.571 | 0 | 12/12 | 1339.4 |
| mixed_75_percent_interactive | native4_b64_noram | 11572.9 | 24982.4 | 1.329 | 0 | 12/12 | 1379.6 |
| mixed_75_percent_interactive | lattice_coalesce2_cached | 3543.6 | 20973.3 | 1.580 | 0 | 12/12 | 1339.0 |
| interactive_arrives_late | native4_b64_noram | 29518.0 | 40551.4 | 0.833 | 0 | 12/12 | 1380.0 |
| interactive_arrives_late | lattice_coalesce2_cached | 15386.9 | 37657.5 | 0.908 | 0 | 12/12 | 1339.3 |

All results, including regressions, failures and nonidentical outputs, are retained in the raw JSONL and analysis.json. One favorable trace is not a workload-level performance claim. Sampled worker RSS is not allocator peak; the hard worker cap is address space. Control-plane RSS is the common benchmark harness, not isolated production gateway memory.

See [primary confirmation](chat_admission_confirmation.md). The candidate is opt-in and a conventional admission heuristic, not a new kernel or stronger language model.

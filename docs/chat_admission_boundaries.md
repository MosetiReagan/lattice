# Chat-framed admission boundaries

These five single-trace diagnostics were fixed before confirmation. They do not determine tuning or replace any primary gate. Both arms use actual model chat framing, identical source inputs/arrivals, greedy sampling, caps and worker resource limits. Empty traffic classes have unavailable P95. There are no confidence intervals from these single traces.

| Case | Arm | Interactive P95 ms | Bulk P95 ms | Tokens/s | Errors | Exact task correct | Worker MiB |
|---|---|---:|---:|---:|---:|---:|---:|
| interactive_only | native4_b64 | 2898.3 | Unavailable | 12.902 | 0 | 12/12 | 1384.0 |
| interactive_only | lattice_coalesce2 | 4164.1 | Unavailable | 9.093 | 0 | 12/12 | 1332.7 |
| bulk_only | native4_b64 | Unavailable | 35585.0 | 0.406 | 0 | 6/6 | 1409.3 |
| bulk_only | lattice_coalesce2 | Unavailable | 37355.8 | 0.401 | 0 | 6/6 | 1397.9 |
| mixed_25_percent_interactive | native4_b64 | 47446.8 | 57748.6 | 0.566 | 0 | 12/12 | 1470.1 |
| mixed_25_percent_interactive | lattice_coalesce2 | 929.2 | 56438.2 | 0.602 | 0 | 12/12 | 1445.5 |
| mixed_75_percent_interactive | native4_b64 | 10415.4 | 22950.0 | 1.446 | 0 | 12/12 | 1382.0 |
| mixed_75_percent_interactive | lattice_coalesce2 | 3505.0 | 20838.3 | 1.602 | 0 | 12/12 | 1360.8 |
| interactive_arrives_late | native4_b64 | 28775.2 | 40652.6 | 0.783 | 0 | 12/12 | 1425.6 |
| interactive_arrives_late | lattice_coalesce2 | 16188.5 | 37696.2 | 0.853 | 0 | 12/12 | 1400.2 |

All results, including regressions, failures and nonidentical outputs, are retained in the raw JSONL and analysis.json. One favorable trace is not a workload-level performance claim. Sampled worker RSS is not allocator peak; the hard worker cap is address space. Control-plane RSS is the common benchmark harness, not isolated production gateway memory.

See [primary confirmation](chat_admission_confirmation.md). The candidate is opt-in and a conventional admission heuristic, not a new kernel or stronger language model.

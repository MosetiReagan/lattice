# Chat-framed admission boundaries

These five single-trace diagnostics were fixed before confirmation. They do not determine tuning or replace any primary gate. Both arms use actual model chat framing, identical source inputs/arrivals, greedy sampling, caps and worker resource limits. Empty traffic classes have unavailable P95. There are no confidence intervals from these single traces.

| Case | Arm | Interactive P95 ms | Bulk P95 ms | Tokens/s | Errors | Exact task correct | Worker MiB |
|---|---|---:|---:|---:|---:|---:|---:|
| interactive_only | native4_b64_noram | 2980.9 | Unavailable | 10.954 | 0 | 12/12 | 1378.8 |
| interactive_only | lattice_coalesce2_cached | 2872.8 | Unavailable | 11.344 | 0 | 12/12 | 1326.1 |
| bulk_only | native4_b64_noram | Unavailable | 37371.5 | 0.412 | 0 | 6/6 | 1379.7 |
| bulk_only | lattice_coalesce2_cached | Unavailable | 37326.0 | 0.426 | 0 | 6/6 | 1339.0 |
| mixed_25_percent_interactive | native4_b64_noram | 47243.5 | 58427.3 | 0.543 | 0 | 12/12 | 1380.5 |
| mixed_25_percent_interactive | lattice_coalesce2_cached | 1878.1 | 57428.9 | 0.574 | 0 | 12/12 | 1339.5 |
| mixed_75_percent_interactive | native4_b64_noram | 10050.6 | 23841.1 | 1.308 | 0 | 12/12 | 1379.6 |
| mixed_75_percent_interactive | lattice_coalesce2_cached | 2195.4 | 21290.5 | 1.496 | 0 | 12/12 | 1339.0 |
| interactive_arrives_late | native4_b64_noram | 29861.1 | 41683.7 | 0.763 | 0 | 11/12 | 1380.0 |
| interactive_arrives_late | lattice_coalesce2_cached | 15938.1 | 41611.5 | 0.775 | 0 | 11/12 | 1339.3 |

All results, including regressions, failures and nonidentical outputs, are retained in the raw JSONL and analysis.json. One favorable trace is not a workload-level performance claim. Sampled worker RSS is not allocator peak; the hard worker cap is address space. Control-plane RSS is the common benchmark harness, not isolated production gateway memory.

See [primary confirmation](chat_admission_confirmation.md). The candidate is opt-in and a conventional admission heuristic, not a new kernel or stronger language model.

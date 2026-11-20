# Admission boundary diagnostics

These are single-trace diagnostics fixed before confirmation completed. They do not replace the frozen primary gate, support confidence intervals, or establish production generalization. No cases are dropped and no policy is retuned from them.

All arms use the same CPU, Qwen2.5 0.5B FP16, greedy sampling, four threads, batch/microbatch256, per-request context2048 and 4096 MiB worker address-space limit. Empty request classes have unavailable P95, not zero latency.

| Case | Arm | Interactive P95 ms | Bulk P95 ms | Actual tokens/s | Errors | Exact task correct | Worker MiB |
|---|---|---:|---:|---:|---:|---:|---:|
| interactive_only | native8 | 966.8 | Unavailable | 96.75 | 0 | 0/12 | 1494.1 |
| interactive_only | lattice_coalesce4 | 1132.2 | Unavailable | 83.51 | 0 | 0/12 | 1383.4 |
| bulk_only | lattice_coalesce4 | Unavailable | 11179.2 | 7.77 | 0 | 0/6 | 1422.9 |
| bulk_only | native8 | Unavailable | 11078.4 | 7.84 | 0 | 0/6 | 1497.2 |
| mixed_25_percent_interactive | native8 | 15530.3 | 17271.1 | 9.13 | 0 | 0/12 | 1544.6 |
| mixed_25_percent_interactive | lattice_coalesce4 | 3856.8 | 17397.9 | 9.07 | 0 | 0/12 | 1469.2 |
| mixed_75_percent_interactive | lattice_coalesce4 | 2311.7 | 6608.9 | 16.60 | 0 | 0/12 | 1397.5 |
| mixed_75_percent_interactive | native8 | 6080.5 | 6165.5 | 17.81 | 0 | 0/12 | 1514.5 |
| interactive_arrives_late | native8 | 11383.1 | 11669.5 | 12.31 | 0 | 0/12 | 1515.3 |
| interactive_arrives_late | lattice_coalesce4 | 9446.8 | 12135.6 | 11.84 | 0 | 0/12 | 1454.9 |
| extra_native_slot_challengers_development_seed | native16 | 11091.3 | 11225.9 | 12.09 | 0 | 0/12 | 1706.9 |
| extra_native_slot_challengers_development_seed | native32 | 11085.7 | 11217.9 | 8.54 | 5 | 0/12 | 2094.9 |
| extra_native_slot_challengers_development_seed | lattice_coalesce4 | 3241.7 | 11697.4 | 11.59 | 0 | 0/12 | 1441.1 |

Output/input/arrival mismatch count against each case's native reference: **5**. Exact task correctness is separate from baseline-output preservation.

The native16/native32 challengers use development seed1002 and are diagnostic only. They extend the finite native slot sweep; they are not additional held-out confirmation sessions. Control-plane RSS in the raw files belongs to the common benchmark harness and is not isolated gateway memory.
The native32 arm returned five generation errors; its private backend diagnostic log reports std::bad_alloc under the fixed address-space cap. It is not a successful compatible baseline under this configuration. Its partial throughput is retained, not treated as a competitive target.

The opt-in 50 ms delay explicitly trades bulk admission latency for burst coalescing. Interactive-only, bulk-only, late-arrival and altered-mix outcomes must all inform deployment suitability. None changes the frozen confirmation decision.

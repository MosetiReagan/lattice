# Concurrent serving results

Three paired CPU sessions, 30 mixed-length workloads per arm/session, identical Qwen2.5 0.5B FP16 weights and greedy sampling. Short work arrives 20 ms after the first long text chunk. Per-request context remains 2,048; total native KV capacity doubles with two slots. This is a fixed synthetic workload study, not a universal throughput claim.

| Metric | Serial mean (ms) | Two-slot mean (ms) | Change | Hierarchical bootstrap 95% interval |
|---|---:|---:|---:|---:|
| short | 1538.51 | 208.36 | -86.46% | [-86.94%, -85.88%] |
| long | 1498.63 | 1590.94 | +6.16% | [+4.19%, +8.13%] |
| makespan | 1617.43 | 1591.37 | -1.61% | [-3.40%, +0.17%] |

| Configuration | Short finished before long | Median sampled worker RSS (MiB) | Worker swap observed |
|---|---:|---:|---:|
| slots-1 | 0/90 | 1306.1 | 0 requests |
| slots-2 | 90/90 | 1332.3 | 0 requests |

All 180 paired performance outputs (long and short) had identical token IDs. The public 22-task smoke study scored 11/22 serial and 11/22 two-slot, with 0 token-sequence mismatches. These finite public fixtures do not establish representative task noninferiority or universal stochastic identity.

Long-request and total-makespan changes are reported alongside the short-request benefit. Native continuous batching, not a custom Lattice kernel, performs the model execution. Admission, explicit slot ownership, verified per-request cancellation and resource constraints are Lattice control-plane contributions.

Full manifests and raw JSONL/CSV are in batching-session-1/2/3. Source is frozen at the recorded commit/worktree. Shared-VM development activity and only three session clusters limit the uncertainty analysis; RSS is sampled, not an exact allocation peak.

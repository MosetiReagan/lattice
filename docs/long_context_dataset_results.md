# Additional 8k-context retrieval observations

This separate CPU run explicitly selects the same 0.5B FP16 weights with an **8,192-token context**, standard greedy inference, seed 84721 and a 32-token output cap. It uses all 60 previously frozen retrieval cases. The original 2k-context baseline and its 24 exclusions are preserved. Different context configurations and coverage must not be presented as a latency optimization or a quality-preserving substitution.

| Nominal base rows | Selected | Scored | Exact correct | Prompt token range | Output-cap finishes |
|---|---:|---:|---:|---|---:|
| 16 | 12 | 12 | 8 | 356–462 | 0 |
| 32 | 12 | 12 | 3 | 648–817 | 0 |
| 64 | 12 | 12 | 2 | 1224–1543 | 0 |
| 128 | 12 | 12 | 4 | 2399–2988 | 0 |
| 256 | 12 | 12 | 5 | 4744–5874 | 0 |

Status counts: `{"completed": 60}`. No input was truncated. Output-cap finishes remain scored; error cases are explicitly excluded from the scored denominator. Success means exact trimmed value/UNANSWERABLE compliance on this synthetic task, not broad long-context comprehension. Twelve cases per tier and shared templates cannot establish population quality guarantees.

[Raw outputs and per-case scores](../benchmarks/results/dataset-long-context-v1/outcomes.jsonl), [configuration and hashes](../benchmarks/results/dataset-long-context-v1/manifest.json) and [summary](../benchmarks/results/dataset-long-context-v1/summary.json) preserve all failures. Row tiers are not token counts; pointer/override templates add a row. This run supports only this tested CPU/model/context configuration, not all models or accelerators. No speed, memory or energy claim is made.

See [dataset cards](datasets.md) and [the original precision study](dataset_results.md).

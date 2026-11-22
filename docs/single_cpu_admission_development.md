# Pinned one-thread development

This is a separate resource envelope: backend threads 1, all benchmark/control/native processes pinned to virtual CPU 0, same Qwen2.5 0.5B FP16 checkpoint, sampling, per-request context and worker cap. The failed raw study and unexecuted four-thread chat draft remain separate. No threshold is relaxed and no development observation is held-out evidence.

The later cache-budgeted held-out protocol is reported separately in [v7 confirmation](chat-cache-budget-confirmation-v7.md). That study uses explicit cgroup bandwidth control and actual per-slot cached execution; its passing result does not reclassify this development sweep or the earlier drafts.

The seed 9001 pinned pilot preserved outputs and strict task correctness 12/12, with candidate/native makespans 38.73/38.32 seconds. The complete seed 9002 tuning sweep below determines two native challengers: lowest interactive P95 and highest aggregate throughput. Distinct best configurations are both retained for confirmation; if they coincide, the thin cost-priority queue is the additional challenger. The thin queue is measured in development regardless.

| Arm | Interactive P95 ms | Bulk P95 ms | Tokens/s | Strict task correct | Output mismatches | Errors | Mean / maximum interval CPU steal |
|---|---:|---:|---:|---:|---:|---:|---|
| native4_b512 | 37801.6 | 37660.0 | 0.898 | 10/12 | 0 | 0 | 0.020 / 0.117 |
| native8 | 33792.2 | 38322.0 | 0.859 | 10/12 | 0 | 0 | 0.025 / 0.108 |
| native1 | 37573.7 | 34861.1 | 0.903 | 10/12 | 0 | 0 | 0.026 / 0.081 |
| native2 | 38482.8 | 37456.7 | 0.881 | 10/12 | 0 | 0 | 0.025 / 0.082 |
| lattice_coalesce2 | 3487.0 | 37553.9 | 0.883 | 10/12 | 0 | 0 | 0.026 / 0.056 |
| simple_cost2 | 13639.1 | 37168.3 | 0.892 | 10/12 | 0 | 0 | 0.029 / 0.079 |
| native4_b1024 | 40730.8 | 40226.9 | 0.834 | 10/12 | 0 | 0 | 0.033 / 0.083 |
| native4_b128 | 32627.2 | 40384.1 | 0.815 | 10/12 | 0 | 0 | 0.028 / 0.062 |
| native4 | 40585.9 | 42018.4 | 0.794 | 10/12 | 0 | 0 | 0.037 / 0.108 |
| native4_b64 | 32110.5 | 45045.2 | 0.729 | 10/12 | 0 | 0 | 0.039 / 0.138 |
| native16 | 43386.8 | 41967.6 | 0.783 | 10/12 | 0 | 0 | 0.034 / 0.071 |

Prospective challengers selected only from this development sweep: `['native4_b64', 'native1']`. Candidate: `lattice_coalesce2`. All recorded results and host spikes remain visible. Development includes source-maintenance activity; no clean-host certification or win is claimed from it. During confirmation, no concurrent tests/builds/model jobs are allowed. Whole-arm mean steal <=5% and every sampled interval <=10% remain hard gates with no exclusions or selective retries.

The tuning-v1 startup was interrupted after an accidental metadata edit. Its data/interruption marker are preserved; it was not used for selection. Tuning-v2 records the fixed runner, settings hash and affinity. This is provenance recovery, not a favorable-result replacement.

The single-CPU draft's confirmation budget remains three sessions of ten paired traces, retaining the earlier study's sample size and performance/output thresholds. It is a new one-thread, chat-framed study, not a repair of the failed four-thread raw study. Every selected native baseline must independently satisfy the same latency and throughput conditions against the candidate. A separately frozen cache-budgeted confirmation later passed its own gates; this draft and development sweep remain unchanged. Results remain scoped to synthetic burst workloads; these conventional heuristics can also be implemented outside Lattice.

## Reproduce development

From a provisioned checkout, use a fresh result directory; existing results are never overwritten. These are development seeds, not held-out qualification.

```bash
LATTICE_CONFIG=configs/single-thread-experiments.json \
  taskset -c 0 uv run --no-sync python experiments/chat_burst_admission.py \
  --output benchmarks/results/new-single-cpu-development \
  --seed 9002 --traces 1 \
  --arms native1 native2 native4 native8 native16 \
  native4_b64 native4_b128 native4_b512 native4_b1024 \
  simple_cost2 lattice_coalesce2
```

Do not run this concurrently with confirmation, tests, builds or another model workload. A fresh preflight must match the intended thread count and CPU affinity; an old passing microprobe does not override the per-arm resource gates.

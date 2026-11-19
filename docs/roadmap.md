# Prioritized engineering roadmap and resource estimates

Planning estimates, updated after Phase B. User authorized implementation with “begin now”; Phase A review gate is satisfied. The CPU vertical slice and benchmark freeze are complete. Independent speculation, prefix and precision studies now exist; the rule controller is restricted to exact measured prompt scope. Integrated evaluation and hardening remain bounded by the limitations below, and 1.0 release is not authorized by the evidence.

## Resource estimates (not measurements)

Raw weight storage estimate = parameter count × bytes/parameter / 2^30. F16: Qwen 0.5B approximately 0.92 GiB; Qwen 1.5B 2.88 GiB; SmolLM 135M 0.25 GiB. BF16 source has similar raw tensor storage. GGUF metadata and format overhead are additional. Ideal 8-bit/4-bit lower bounds are half/quarter of F16; real grouped formats have scales, mixed tensors and padding, so do not quote these as file sizes.

F16 KV estimate = 2 × layers × KV heads × head dimension × tokens × 2 bytes. Qwen 0.5B: 12 KiB/token, 24 MiB at 2,048. Qwen 1.5B: 28 KiB/token, 56 MiB at 2,048. These are dense single-sequence tensor estimates derived from configs, not RSS measurements; backend padding, allocated context pools, scratch, fragmentation and concurrent slots add memory. At config max 32,768 the estimates become 384/896 MiB. Reservation must use the actual allocated pool, not observed prompt length alone.

Start with a proposed 5 GiB worker memory ceiling and >=2 GiB host reserve, then revise from measured load/peak allocation; refuse unsupported hard-limit guarantees. A 0.5B F16 worker is plausible. A 1.5B target plus 0.5B draft has ~3.8 GiB raw weights before KV/scratch and could exceed the safe worker budget. Run sequentially first; speculation remains conditional. No claim that a 4B F16 model fits: raw weights alone are ~7.45 GiB.

Disk planning: two source snapshots plus two F16 conversions require ~7.6 GiB raw weight storage, before quantizations, build tree, temporary files and optional dependencies. Budget roughly 10–14 GiB total for a carefully sequential CPU workflow, which is tight with 15 GiB currently free. Enforce a free-space check and reserve >=3 GiB; download/convert one model at a time, never delete user data. Keep artifact hashes and preserve baseline GGUF/run records. A 30 GiB additional storage allocation is an optional recommendation for comfortable multi-format research, not authorized provisioning. Avoid CUDA wheels and duplicate model caches on this box.

Compute/runtime duration cannot be predicted responsibly without first tokens/sec and load-time measurements. Pilot one model, 2 lengths and 3 repeats; estimate full run wall time as sum of measured prefill + generated_tokens/decode_rate plus load/warmup/quality overhead. Do not present that projection as a measured result. Future GPU experiments may benefit from a 16–24 GiB NVIDIA GPU, >=16 GiB host RAM and >=50 GiB disk, but no procurement, rental or GPU support claim is made. Energy requires power instrumentation, not just a GPU counter assumption.

## Milestones and exit checks

| Order / phase | Concrete work | Exit criterion | Planning effort |
|---|---|---|---|
| 0 / A review | Review these documents, CPU/backend/model choice, tolerances and storage plan | Recorded review before large implementation | Accepted by user; completed |
| 1 / B first slice | Install minimal build tools, pin/build llama.cpp, provision one safe F16 model, basic Python adapter, CLI generation | Real Qwen 0.5B tokens, bounded output, accurate backend identity and JSON timing record | 2–4 engineer-days |
| 2 / B serving | Streaming CLI/API, registry, health/model endpoints, validation, auth configuration, timeout/cancellation | End-to-end smoke tests plus disconnect cleanup and failure isolation | 3–5 days |
| 3 / C baseline freeze | Artifact lock, prompt datasets, runner, quality scoring, raw JSONL/CSV and machine manifest | Independently rerunnable CPU baseline with actual results, no optimizations | 4–7 days |
| 4 / D1 speculation | Greedy draft/target compatibility and verification, configurable draft length, acceptance telemetry; reference sampling math separately | Independent tests and controlled baseline comparison; negative benefit allowed | 5–10 days |
| 5 / D2 KV policy | Exact tenant-scoped prefix identity, limits/eviction/statistics, backend cache controls | Isolation/invalidation tests and repeated-prefix ablation | 4–7 days |
| 6 / D3 precision | F16/Q8_0/Q4_K_M artifacts, capability probes and measured quality tables | Same-source precision study and explicit unknown/rejected paths | 3–6 days |
| 7 / D4 scheduling | Admission/backpressure, reservations, cancellation, fair concurrency; delegate native batching | Overload/mixed-length/timeout tests, no leaked reservations | 4–7 days |
| 8 / D5 routing | Immutable variant registry, task-evidence requirements and explicit aliases | Held-out quality-cost routing evaluation and explanations | 4–7 days |
| 9 / E controller | Deterministic versioned policy with features, estimates, feedback, confidence/evidence coverage | Constraint-invariant tests and held-out/live policy comparisons | 5–10 days |
| 10 / F integrated evaluation | Individual/combined/adaptive ablations and interaction analysis | Raw records, confidence intervals, quality acceptance per stratum | 5–10 days plus measured compute |
| 11 / G hardening | API/CLI coverage, quotas, fuzzing, recovery, tested hardware paths | Concurrency, security and recovery matrix; untested hardware explicit | 5–10 days |
| 12 / H release | Complete docs, notices/license, reproducibility audit, gate review | All G1–G10 pass before 1.0/tag/publication | 2–4 days |

Rough total 46–87 engineer-days after review, excluding hardware access, failed experiments and exact stochastic runtime implementation. These are labor planning ranges, not compute measurements or a promise. Dashboard is deliberately after records and baseline, optional until profiling data exists. Full mathematically exact stochastic speculative support may require a deeper adapter and additional work; it cannot be declared complete from a greedy experiment.

## Test strategy

Separate deterministic unit tests, mocked adapter tests, real CPU integration and real accelerator runs in reports. Unit coverage: constraints, routing evidence, cache compatibility/eviction, scheduler reservations, metrics and speculative acceptance/residual math. Integration: actual checkpoint load, tokenization identity, normal/streamed generation, output caps, cancellation, isolated worker failure and cache correctness. Compare each optimization independently before controller integration. GPU mocks establish no GPU support.

Implement the required API/CLI surface incrementally. Benchmark execution is an authenticated, bounded admin job rather than unbounded work in a request handler. Later profile/optimize/compare commands report only actual evidence or unknown status. No learned policy until held-out execution outcomes support it.

## Remaining risks

Accepted initial design choices: llama.cpp CPU first, Qwen pair, one resident worker initially, approximate-path quality margins, and Apache-2.0 recommendation. Repository access remains unresolved; local work is reviewable without remote write access. Limited disk and target+draft RAM may force smaller experimental contexts or external hardware, never silent user-request truncation. Exact stochastic sampling over a server-only API is an explicit feasibility risk. No release date should precede G7 evidence of a repeatable resource improvement.

## Current implementation audit

- A/B: complete for the tested CPU vertical slice.
- C: frozen executable source, manifests, raw JSONL/CSV, eight workloads and three standard sessions; shared-VM isolation remains a limitation.
- D: native greedy speculation, logical prefix control and same-source quantized variants have independent tests/comparisons. Priority admission and explicit model switching work; continuous batching and broad learned/task routing do not.
- E: deterministic rules-1 with identity/hardware/thread/input-scope gates, actual feedback and versioned evidence. Unknown quality/cost stays standard or fails explicitly under hard budgets.
- F: three paired prefix sessions plus precision quality study; integrated adaptive ablation uses new executions of known prompts, not generalized held-out quality.
- G: cancellation, timeouts, model/hash failure, parent death, request limits, auth/rate limits and queue handoff have tests. Multi-active fairness, GPU/MPS and external recovery audits remain incomplete.
- H: no 1.0 tag/publication. Q4 quality loss, limited substitution evidence and non-preemptive serving remain real acceptance concerns.

All earlier labor/storage figures were estimates. Actual artifact sizes, observations and failures appear in the experiment manifests/results; negative outcomes do not reduce acceptance criteria.

# Measured development results and release gates

These are real CPU development measurements, not Lattice 1.0 or production guarantees. Raw manifests, JSONL, CSV and source locks are retained under benchmarks/. No estimated value is placed in a measured result column.

## Frozen standard runtime

Four CPU threads, official Qwen2.5 0.5B FP16 GGUF, 2,048 context, greedy output caps, no cross-request cache reuse. Sessions run from frozen standard source commit 255e1e1. Each completed session has three warmups and 30 observations per category; native EOS can end output before the cap.

| Workload | Completed observations | Median request latency (ms) | Mean sampled worker RSS (MiB) |
|---|---:|---:|---:|
| short | 90 | 262.96 | 1298.6 |
| long_prompt | 90 | 1566.23 | 1314.0 |
| short_response | 90 | 240.31 | 1305.8 |
| long_response | 90 | 1933.46 | 1306.2 |
| repeated_prefix | 90 | 964.28 | 1313.5 |
| concurrent | 90 | 1366.26 | 1301.4 |
| mixed | 90 | 1324.56 | 1331.3 |
| memory_constrained | 90 | 419.52 | 1305.8 |

Completed standard sessions: [1, 2, 3]. Concurrent/mixed latency includes queue wait in a serial worker; these rows are not single-request decode latency. Sampled worker RSS is not exact allocator peak or per-request incremental memory. See raw summaries for means, standard deviations, P90/P95, actual token counts and throughput. P99 is unavailable below 1,000 observations.

## Same-weight warmed-prefix experiment

Both arms receive one unmeasured identical priming request per measured trial, in randomized arm order. Three sessions, 90 paired trials per category, no greedy token mismatches. This measures warmed prefix reuse through llama.cpp, not a new kernel or superiority over an already tuned native prefix-cache baseline.

| Workload | Paired trials | Mean latency change | Hierarchical paired bootstrap 95% interval |
|---|---:|---:|---:|
| short | 90 | +0.63% | [-6.98%, +9.27%] |
| long_prompt | 90 | -84.82% | [-85.60%, -83.85%] |
| repeated_prefix | 90 | -76.04% | [-77.35%, -74.50%] |

Long/repeated prefixes show a repeatable improvement in this narrow warmed scope; short prefixes do not show a reliable improvement. No total-workload amortized gain including priming, universal quality equivalence or energy saving is claimed. Shared VM/development activity was not fully isolated; original runs lack worker-swap histories. These limits remain in the report.

## Precision and quality

From one controlled representation session: FP16 WikiText subset PPL 21.8762 and 11/22 public smoke tasks; Q8 PPL 22.0205 (+0.66%), 11/22; Q4 PPL 22.7338 (+3.92%), 10/22. The subset uses 32 chunks of 256 tokens. Q4 fails the proposed 2% PPL tolerance. Q8 is not automatically qualified by only 22 public tasks. Detailed measured artifact bytes, timings and memory are in quantization_analysis.md and the precision raw records.

## Speculative and adaptive execution

| Draft length | Trials per arm | Standard median (ms) | Speculative median (ms) | Accepted / proposed |
|---|---:|---:|---:|---:|
| 1 | 30 | 1592.21 | 2907.02 | 880 / 990 |
| 2 | 30 | 1470.63 | 2639.36 | 1190 / 1360 |
| 4 | 30 | 1597.61 | 2625.15 | 1400 / 1870 |
| 8 | 30 | 1517.92 | 2448.86 | 1560 / 2440 |

Greedy mismatches: 0. Same Qwen 1.5B Q8 target in both arms, Qwen 0.5B FP16 draft, context 1,024. Blocks are randomized per draft length; this one-session block design does not eliminate time-order confounding. Draft/verification-only latency and target-pass counts are unavailable.

| Workload | Standard median (ms) | Adaptive median (ms) | Adaptive selected paths |
|---|---:|---:|---|
| short | 228.16 | 220.13 | {"cached": 0, "speculative": 0, "standard": 30} |
| long_prompt | 1508.06 | 217.55 | {"cached": 30, "speculative": 0, "standard": 0} |
| repeated_prefix | 932.50 | 212.96 | {"cached": 30, "speculative": 0, "standard": 0} |

These are new executions of already-qualified exact prompt hashes, not held-out prompt generalization. Unknown prompts remain standard; no precision/model downgrade is automatic.

## Release classification

**Unreleased development build, not Lattice 1.0.** G1 real inference and G2 the narrow tested CPU backend are established. G3 has preserved source/artifact locks and repeated standard observations, subject to the isolation limitations above. G4 has independent native greedy speculation, logical prefix control and quantized execution studies with unit/CPU evidence. G5/G6 qualify only a narrow exact-prompt greedy policy, not broad quality-aware routing. G7 shows warmed-prefix improvement against the fixed standard baseline, attributed to backend reuse. G8 remains incomplete because serving is non-preemptive single-active-request admission. G9/G10 have documentation/reproduction assets but no remote release/reproduction audit.

Q4 quality failure, absent representative substitution evidence, limited adaptive scope, untested accelerators and non-preemptive serving are real remaining release concerns. Acceptance criteria have not been lowered, and no 1.0 tag or release has been published.

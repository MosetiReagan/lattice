# Changelog

## Dataset intake-v1 — unreleased evaluation infrastructure

- Pinned nine external dataset families / ten configurations with source licenses, file hashes and data-only loading.
- Prepared 183,241 external records with duplicate/group isolation and a preserved quarantine audit.
- Added 10,400 deterministic arithmetic, JSON, instruction and retrieval cases, canonical-reference checks and stratified policy partitions.
- Added versioned generated-answer scorers, frozen 600-case evaluation subsets and reproducible corpus-loss/tokenizer/quality studies.
- Kept official IFEval and sandboxed code execution explicitly deferred; retained the original smoke suite and precision study.

## 0.3.0.dev0 — unreleased concurrent CPU serving

- Added opt-in two-slot llama.cpp continuous batching with fixed per-request context and one resident model.
- Replaced serial-only admission with bounded, cancellation-safe priority semaphore admission.
- Added internal stream IDs, private native cancellation/idle confirmation, quarantine/draining and peer-preserving worker recovery.
- Verified native cancellation controls/context layout before accepting concurrent work; kept serial policy/precision evidence out of this mode.
- Added real runtime/HTTP cancellation, prefill-timeout and short-versus-long isolation tests.
- Preserved three paired 30-trial serving sessions, exact greedy comparisons, public smoke quality checks and all measured trade-offs.
- Kept automatic precision substitution disabled and the release classified as development work.

## 0.2.0.dev0 — unreleased research build

- Preserved executable standard source, artifact locks, eight workload categories, repeated observations, JSONL/CSV and an external pinned WikiText subset.
- Added exact full-distribution speculative reference tests and native greedy draft/target experiments, keeping negative performance outcomes.
- Added exact identity/tenant/TTL/byte-aware prefix eligibility and three-session greedy comparisons.
- Derived and evaluated Q8/Q4 variants from the frozen source; rejected Q4 automatic selection on measured quality loss.
- Added versioned exact-prompt evidence gating, resource checks, execution feedback and explicit registered-model switching.
- Added cancellation-safe priority/aging admission, address-space budgets, authenticated bounded profiling jobs and parent-death worker cleanup.
- Added real-data dashboard export and explicit CLI benchmark/profile/optimize/compare workflows.
- Retained the shared-VM isolation limits, small quality scope, unsupported stochastic native speculation/accelerators and non-preemptive serving as release concerns. No 1.0 release.

## 0.1.0.dev0 — Phase B baseline

- Real pinned CPU llama.cpp/Qwen FP16 generation, streaming API/CLI and structured timings.
- Artifact/input/context/output checks, auth, rate limits, queue, deadlines and cancellation/reload.
- Unit and real CPU/HTTP integration tests; Apache-2.0 for original code.

## Phase A

- Environment and upstream research audit, architecture, license recommendation and staged roadmap.

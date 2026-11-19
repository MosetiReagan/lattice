# Proposed architecture — Phase A

Phase A design, updated after Phase B implementation. The CPU runtime, experiment foundation and initial policy/cache/precision/routing/admission modules are implemented; see baseline_runtime.md and component documents for tested scope. Physical native kernels/KV and token batching remain backend responsibilities. Learned policy, broad automatic routing and multi-active serving remain proposed.

## Minimal first vertical slice

CLI → validated generation request → one registry entry → llama.cpp subprocess → streamed tokens and timings → JSONL record. Add a small HTTP API once the same generation path works. Keep one Python process plus a private backend worker; bind worker to loopback. No microservices, dashboard, plugin system, learned policy or GPU kernel initially.

Start with only request/result types and a backend adapter exposing capabilities, load, tokenize, generate-stream, cancel, health and unload. Capabilities must distinguish verified, advertised, and unavailable. Use native backend timings only where actually exposed; wall-clock HTTP time is not decode time. A Python 3.12 environment may be preferable for later ML wheels; first wrapper can use available 3.13 with dependency checks.

## Extension boundaries after baseline freeze

```text
Gateway / CLI -> validation + tenant identity -> bounded admission queue
 -> analyzer -> deterministic planner -> registry + reservations + cache policy
 -> backend worker (native batching, kernels, KV storage)
 -> stream validator -> response
                         -> execution record -> evaluation -> versioned policy evidence
```

Planner consumes immutable request features, a resource snapshot, capability records and measured profiles. It must never import a backend implementation. A plan identifies model/checkpoint/tokenizer hashes, backend build, precision, strategy, sampling, context cap, draft configuration, memory reservation, cache namespace and reason/confidence/evidence ID. A missing cost profile cannot be presented as a measured estimate. Unknown paths remain opt-in experiments.

Suggested later package layout: `src/lattice/{backends,runtime,controller,routing,cache,quantization,scheduler,observability,evaluation,optimizations/speculative,api}`, `cli/`, `benchmarks/`, `configs/`, `tests/`. Use one namespaced Python package rather than unrelated top-level modules. These directories are not implemented by this document.

## Constraints and decisions

- Model identity and sampling are hard constraints. Explicit model IDs cannot silently become smaller models. Cross-model routing needs a user-selected alias and task-class quality evidence.
- Hard memory admission includes resident weights, KV pool, draft, scratch, backend overhead, other active reservations and host reserve. Check process RSS/available memory before admission; estimates alone cannot guarantee allocation success. Use worker process limits and OOM isolation. No implicit truncation or output-token reduction.
- Infeasible requests return an actionable resource/constraint error; a fallback is allowed only if explicitly compatible with all user constraints. Latency budgets are targets unless an enforceable deadline is requested; record misses.
- Backend owns physical KV allocation and token batching. Lattice owns quotas, logical lifecycle, safe reuse identity, tenant fairness and admission. Never claim a custom paged allocator when delegated.
- Prefix identity includes tenant, exact token sequence, checkpoint and adapter hashes, tokenizer/chat-template revision, RoPE/positions, attention mask, KV dtype/layout, backend/build and execution settings affecting prefill. Check exact metadata/tokens after hashes; invalidate on mutation. Disable cross-tenant reuse initially. Never expose native slot-save filesystem endpoints publicly.
- Initial scheduling: bounded FIFO, one active request; later bounded concurrent slots and aging/round-robin admission. Close/disconnect is not proof of cancellation: test backend stops token generation and releases reservation.
- Fixed precision per resident worker initially. Variant swapping has load/eviction cost; account for it before routing. Quantization is not a per-request universal flag.
- Greedy speculation initially. A later probability-level implementation must pass analytical finite-vocabulary and empirical distribution tests; use a reference adapter when the server cannot expose verification probabilities. Document it as Lattice logic only when implemented.
- Output validation handles token counts, finish reasons and SSE terminal events; it does not establish factual correctness.

## Security design

Allowlist model artifacts with immutable revisions and SHA-256; prefer safetensors/GGUF, no remote Python execution or pickle loading. Validate paths at operator-only provisioning; API never accepts arbitrary paths/URLs, shell code or cache filenames. Bound body bytes, prompt tokens, max output, queue size, concurrency and benchmark work. Request timeout/cancellation must propagate. Protect inference with optional configured API keys and rate limits; admin benchmark/model-management endpoints require operator authorization. Audit IDs and decisions without prompt text/secrets by default. Do not expose host inventory in public health/metrics. Reject unsupported fields rather than silently changing sampling.

## Observability and quality contract

Execution records include config/dataset/artifact hashes, seed, timings, actual strategy and fallback, provenance, queue time, token counts, sampled process memory (with sampling resolution), errors and quality outcome. Use null plus reason for unavailable GPU utilization, energy, cache bytes or phase timings. JSONL is canonical; CSV is an export. Dashboard comes after real records exist.

Policy minimizes measured estimated cost over compatible paths, subject to approved task-quality tolerance and hard constraints. Report confidence as evidence coverage/calibration, not arbitrary model confidence. Version policies and retain outcomes. No online learned override. Evaluate against pinned fixed-backend baseline and task-stratified held-out prompts. Quality regressions or uncertain resource estimates disable automatic selection.

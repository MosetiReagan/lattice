# Lattice trial with KaziAI's existing 8B model

Tested 24 November 2026. **Lattice runs the existing model and provides useful priority admission under saturation. It requires integration work before serving KaziAI business agents.** Native two-slot serving provides the same ordinary-concurrency improvement with the existing tool-call interface.

## Setup and scope

- Isolated test VM: 8 AMD EPYC vCPUs, 32 GiB RAM, Linux x86-64, no GPU. No production credentials or business database were copied.
- Model: the exact existing `Qwen3-8B-Q4_K_M.gguf`, SHA-256 `d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785`.
- Native executable/shared libraries copied from KaziAI's existing build, commit `54cde7106a6b4013a053f13bb4a5d91683e7338d`, reporting 0.9.0-dev.
- Lattice source: `4fd5276480b4730240d3011bceac02e69839d1e8`, plus the isolated cancellation ownership fix in [scheduler.patch](evidence/scheduler.patch).
- Four inference threads, 8,192 context tokens per slot, Q8 KV, thinking disabled, flash attention enabled. Initial model load and warmup excluded from timings; reloads caused by preemption included. All arms disabled prompt/archive caching to isolate admission behavior. The copied binaries required an explicit library search path.
- Native controls called the real native HTTP completion endpoint directly. Lattice arms called its real streaming chat HTTP endpoint. Native model startup used the same artifact checks and worker memory ceiling in both paths. Matching model/backend/core settings does not make this a full production-app latency benchmark; production mlock behavior and prompt-cache defaults were not reproduced.
- Synthetic business summaries capped at 96 tokens; brief English arithmetic and Kiswahili customer/amount requests. Three repetitions per language per arm: 30 main traces, 60 foreground/background completions. Additional saturation, cancellation, tool-schema, output-budget, receipt and sampling probes.
- No simulation fallback. The bundled benchmark's fallback path was deliberately avoided. Full raw records and the harness are in [evidence](evidence).

## Measured results

Medians in seconds. First-token time means the client observed actual nonempty generated text, including queueing and prefill. These are three-repeat pilot medians, not P95/P99 or production guarantees.

| Serving path | Slots | English first token | Kiswahili first token | Background completion |
|---|---:|---:|---:|---:|
| Native control | 1 | 10.02 | 10.26 | 14.72 |
| Lattice FIFO | 1 | 9.85 | 10.77 | 14.80 |
| Lattice preemptive | 1 | 6.11 | 6.59 | 28.02 |
| Native control | 2 | 1.28 | 1.71 | 17.35 |
| Lattice preemptive | 2 | 1.26 | 1.76 | 17.28 |

Single-slot preemption improved the English first-token median by about 39%, while the background median rose about 90%. The worker restarts and repeated prefill explain much of that cost. Ordinary two-slot concurrency is the larger first improvement for the current single-slot deployment; Lattice and native serving were similar with a slot available.

In the separate **one-trace, two-background saturated probe**, native two-slot serving took **17.26 s** to first token versus **1.86 s** with Lattice preemption. Both answered the arithmetic question correctly. The slowest background completed in **28.40 s** natively versus **34.03 s** with Lattice, about a 20% increase. This shows the mechanism working in that scenario; it does not establish prevalence or tail-latency guarantees.

## Output quality and compatibility

- All main greedy background summaries and interactive outputs matched the native single-slot control byte-for-byte in the recorded comparisons. Arithmetic answers were correct; Kiswahili responses retained the specified customer and amount. Some wording echoed an instruction, and summaries reached the output cap, so this is not broad language/quality certification.
- At KaziAI's default temperature **0.2**, a separate three-seed reminder-draft probe matched in two cases and differed in one. The changed output retained the visible invoice/customer/amount facts but changed wording. Automatic resume therefore should not be advertised as universally seed/output preserving. See [sampling-comparison.json](evidence/results/sampling-comparison.json) and [sampling.json](evidence/results/sampling.json).
- The first receipt prompt left numeric formatting unspecified. Every serving path returned the same currency-prefixed strings for amounts. A later prompt explicitly required numeric fields, but **both native and Lattice returned total 1000 instead of the tax-inclusive 1160**. These failed probes are retained, not scored as passes. Lattice changes serving behavior; it does not remedy this model's financial interpretation error. Financial schemas, semantic validation and independent approval remain necessary.
- Native one- and two-slot controls produced structured `search_customers` tool calls with HTTP 200. Every Lattice arm rejected `tools`/`tool_choice` with HTTP 422. Tool-role messages are also absent from its schema. This blocks replacement of KaziAI's agent inference endpoint without API/streaming work.
- Lattice rejected a 1,024-token output request with HTTP 422. Its 512-token limit is compatible with the current default, but not all output budgets KaziAI permits.

## Cancellation, resources and code changes

The added two-slot cancellation-after-handoff regression failed on the original scheduler: cleanup removed a different live owner's permit. The isolated fix stores and releases the exact granted permit. The existing non-integration suite passed **166 tests**, with two skipped and 20 real-model integration tests deselected; after adding the fix/regression, **167 passed**, with the same skips/deselections. The old integration fixtures target other model artifacts; the real 8B pilot was run separately.

Every serving arm preserved the tested peer and recovered after a client cancelled a stream. The Lattice two-slot path recorded two verified native cancellations, zero unconfirmed cleanup, zero quarantined leases and zero worker retirements. These are bounded checks, not exhaustive lifecycle certification. Native control success establishes peer completion/recovery, not a measured native cancellation-acknowledgement latency.

Observed worker high-water memory was approximately **5.38 GiB** for one-slot Lattice and **5.98 GiB** for two-slot serving, with no swap observed. The resource observer missed the native single-slot arm and part of FIFO; unavailable observations remain null. Maximum aggregate CPU steal over a recorded trace was below 0.02%. This was one host and fixed arm order, with no independent hardware reproduction or universal OOM-safety claim.

## Recommendation for KaziAI

1. **First practical improvement:** qualify native two-slot serving through KaziAI's actual agent workflows. Preserve 8,192 tokens per slot, which means a 16,384-token total context at two slots. The pilot retained native tool-call capability and delivered the ordinary-concurrency improvement without adding another public API contract.
2. **Use Lattice when priority under saturation is required:** its two-slot preemption had a substantial benefit in the tested two-background case. Apply the cancellation fix and implement tool-call/message/streaming compatibility before routing business-agent traffic through it. Resumption at nonzero temperature needs additional qualification or restrictions.
3. **Text-only pilot integration is feasible:** report and summary drafting can fit its supported API subset. Keep current financial validation and approval gates; do not interpret faster output as more accurate business reasoning.

The live KaziAI model, backend endpoint, frontend and business records were not changed. Temporary test VMs were removed after evidence collection, the production VM's original network membership was restored, and the live app/inference services remained active with HTTP 200 afterward. No repository push, production rollout or external customer communication occurred.

Reproduction materials: [benchmark.py](evidence/benchmark.py), [sampling_probe.py](evidence/sampling_probe.py), [test_scheduler_regression.py](evidence/test_scheduler_regression.py), [summary.json](evidence/summary.json), [results.csv](evidence/results.csv), source hashes in [manifest.json](evidence/results/manifest.json). The report's conclusions apply to these recorded settings and workloads.

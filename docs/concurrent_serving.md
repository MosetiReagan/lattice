# Concurrent CPU serving

The two-slot adapter uses llama.cpp's native continuous batching. Lattice supplies bounded priority admission, explicit slot leases and per-request lifecycle/resource checks. It does not implement a token scheduler, attention kernel or a new batching algorithm.

```bash
uv run --no-sync lattice serve --model qwen2.5-0.5b-instruct-f16 --native-slots 2
```

One model and precision stay resident for the worker lifetime. Per-request context remains 2,048 tokens: the native worker gets 4,096 total tokens across two slots, and startup verifies each native slot's context. Thread count and the shared worker address-space ceiling do not double. Additional dense KV capacity is included in admission estimates. One-slot mode remains available for explicit model switching, cached execution and greedy speculation; those paths' quality/performance evidence is not applied to two-slot serving.

Concurrent requests use standard execution. Optimized-mode requests either receive an explicit standard fallback explanation or fail when allow_fallback=false. A request cannot lower a running shared worker's memory ceiling and interrupt peers; a tighter requested cap fails explicitly. Unknown model KV accounting disables concurrent startup. Current validated capacity is one or two slots, not arbitrary parallelism.

## Cancellation and failure ownership

Every generation gets an internal random native conversation ID and an explicit slot lease. The ID is not copied from client headers. After a response ends or is cancelled, Lattice uses the pinned backend's private stream DELETE endpoint, then verifies that the leased slot is idle before returning it to admission. Startup probes the stream lookup/delete controls and native slot/context layout. Unsupported backend versions fail rather than claiming isolated cancellation.

If native ownership cannot be confirmed, the slot is quarantined. Existing peers may finish; new backend work waits while the worker drains. Once all live user streams have drained, the worker can retire and reload without terminating another user's active response. Quarantine, verified cancellation and drained-retirement counters appear in metrics without exposing conversation IDs or private output buffers. Native slot/stream endpoints are not proxied through the public Lattice API.

The adapter passes leases explicitly through the generator: HTTP preflight and SSE delivery may run in different tasks. A context-variable implementation failed the first HTTP test and was replaced; the failure logs and corrected regression tests are retained. Direct runtime tests alone were insufficient to establish this boundary's correctness.

## Evidence scope

Real CPU tests cover a short request completing during a long request, cancellation of one stream while a peer completes, timeout during prefill, unchanged worker PID, per-slot context limits, shared-budget rejection and live HTTP/SSE disconnect isolation. Unit tests cover semaphore bounds/aging/cancellation handoff and quarantine without killing a simulated peer. Mocked process metadata is never used as hardware evidence.

The mixed-length benchmark compares one and two slots using identical FP16 weights, sampling, per-request context and public prompt variants. Short work arrives 20 ms after the first long text chunk. Actual EOS/output token counts are retained. Both workers are resident, but only one arm executes at a time; arm order is randomized within paired trials. Model loading and three warmups per arm are separate from request timing. Raw worker RSS and VmSwap samples, queue/TTFT/total latency, long completion latency, workload makespan and throughput are recorded.

The pilot also compares complete greedy token sequences across the 22 public smoke tasks. This is finite equivalence evidence, not a representative held-out quality result or a claim of stochastic distribution identity. Only Qwen2.5 0.5B FP16 on this CPU is measured for concurrent performance here. More slots, other precisions, cached/speculative combinations and accelerator serving remain unqualified.

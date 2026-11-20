# CPU admission experiments

## Scope and defaults

These operator-selected policies change queue/admission behavior, not model weights, tokenization, sampler, output limits or native kernels. The default remains `priority_fifo` and one native slot. They do not select a smaller or quantized model. Configuration remains explicit; no experimental policy silently replaces an existing choice.

| Policy | Behavior | Status |
|---|---|---|
| priority_fifo | Explicit priority, aging and FIFO ties | Existing default |
| priority_cost | Same priority/age first, then smaller byte/output-cap proxy | Development experiment |
| priority_cost_reserve | Reserve one lane from default-priority bulk; bounded small-burst drain hold | Development experiment; throughput trade-offs retained |
| priority_cost_coalesce | Cost ordering plus a 50 ms grace for default-priority bulk | Frozen confirmation candidate |

The proxy is input UTF-8 bytes plus 64 times the requested output-token cap. It is a queue tiebreaker, not validated FLOPs, dollars, GPU time, or task complexity. Explicit priorities and aging outrank the proxy. A bulk request has more than 1,024 input bytes or requests more than 32 output tokens. In the coalescing candidate, higher-priority requests bypass the grace. The delay counts toward request deadlines and measured latency; it never changes requested tokens or drops work.

The 50 ms grace lets a nearby interactive burst enter native slots before expensive prefills. This is a conventional bounded admission heuristic. It must not be presented as a novel attention kernel or a guarantee that all short requests finish sooner. It can add delay to bulk-only traffic and is unsuitable for some arrival patterns. Native continuous batching remains llama.cpp functionality.

## Measured development

Preserved pilots are under `benchmarks/results/burst-admission-dev-*`:

- Cost ordering at two and three slots reduced interactive latency but missed the throughput budget.
- Four-slot reservation traded off tail latency and throughput; its refinements were not promoted.
- A 50 ms grace with four slots looked promising on development seed 1002 while preserving outputs.
- Native 1/2/3/4/8 slots and native8 logical batch sizes 64/128/256/512/1024 were tried. The chosen native confirmation baseline uses eight slots and batch/microbatch 256, which had the best development interactive P95 in the finite sweep.

All negative pilots remain available. Development selection is not independent confirmation. The frozen held-out protocol is `benchmarks/workloads/burst-coalescing-confirmation-v1.json`; it requires three sessions, unchanged gates and hierarchical paired uncertainty. The [completed confirmation failed](burst_admission_confirmation.md) exact-output preservation. A separately versioned chat-framed study cannot retroactively change that outcome.

Confirmation and boundary measurements used runtime commit `1aef95a` and their recorded source hashes. A subsequent admission guard bounds all outstanding requests (including grace/drain waiters) by native capacity plus `max_queue`, even while native slots are free. Cancellation releases this budget. The twelve-request measurements used `max_queue=128` and never reached the guard, but are not relabeled as measurements of the patched source. New experiments record their own source manifests.

## Transport profile

A 40-construction no-network pilot identified repeated trust-store loading in HTTP client setup. A separate 12-request real CPU profile measured a median about 6.6 ms in client construction within about 118 ms total. These profiles are instrumentation evidence, not an inference speed claim.

The implementation reuses one verified SSL context, retaining certificate verification and ignoring environment proxies/trust overrides as before. Clients, credentials, headers, conversations and prompt state remain request-scoped. Cancellation acknowledgement, private native stream controls, context/token checks and memory admission remain in place.

## Explicit configuration

```bash
lattice serve --model qwen2.5-0.5b-instruct-f16 \
  --native-slots 4 --admission-policy priority_cost_coalesce
```

Native slot options include 1/2/3/4/8; host memory admission still applies. Only the measured CPU/model/configurations have evidence, not arbitrary hardware or models. Default batch/microbatch remains 256. Operator registry fields `batch_tokens` and `ubatch_tokens` allow explicit tuning, rejecting a microbatch larger than the logical batch.

Mocked tests cover priority preservation, FIFO/cost ties, aging, invalid cost inputs, cancellation during grace/drain waits and permit cleanup. Real CPU tests cover multi-slot generation, output bounds and peer-preserving cancellation. Full confirmation additionally checks request-for-request equality against the tuned native baseline.

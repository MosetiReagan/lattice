# Experimental concurrent prefix eligibility

This opt-in extension uses a separate existing `PrefixCache` ledger for every exclusive native slot lease. llama.cpp still owns the KV tensors, prefix verification and physical allocator. This is not a new cache kernel or a claim of lower physical KV allocation.

Both permissions are required: operator setting `concurrent_prefix_cache=true`, and request `optimization.mode="cached"`. Defaults remain disabled/standard. The configured cache budget must cover the complete **estimated dense KV capacity** of the worker's slots; model weights, graph buffers and allocator overhead remain under the separate hard worker address-space ceiling. Metadata is an estimate of eligible dense KV, not a measured allocator peak.

An explicitly cached request can reuse only an identical token prefix with the same model/checkpoint, tokenizer, backend, per-request context, KV type and positional configuration in its own slot ledger. All requests belong to the existing single authenticated operator realm; this does not add a multi-tenant authentication API. Mutually untrusted tenants require separate worker/authentication realms. No prompt text, response text or KV tensor contents are exposed through cache statistics.

A standard request invalidates its leased ledger and sends `cache_prompt=false`. A subsequent cached request therefore cannot inherit eligibility from that standard request. Failed/cancelled work invalidates its slot. Restart invalidates all ledgers. Existing TTL and token/byte checks apply independently to each slot. Explicit native slot IDs prevent Lattice from assigning a different request's ledger to a slot.

For cache-enabled concurrent workers, the optional native global RAM prompt archive, idle-slot snapshots and chunk-reuse feature are disabled. Only direct per-slot compatible prefix reuse is enabled. This avoids native cross-slot restores bypassing Lattice's per-slot eligibility/accounting. Native baselines retain their own configurations; development additionally tests an upstream RAM-archive-disabled native challenger rather than assuming that default settings are optimal.

Per-request strategy and eligibility are local to the lease. Cached and standard requests do not mutate a shared strategy variable, draft model, precision or worker memory ceiling. Generation constraints and output limits remain unchanged.

Real CPU tests verify repeated-slot native reuse, standard-mode invalidation, identical greedy outputs, mixed-mode metadata, peer-preserving cancellation and restart cleanup. Unit tests verify explicit permission, complete-pool budget checks, slot separation, incompatible identity rejection, unapproved payload rejection and cancellation invalidation. No mocked test establishes GPU support or an inference speed improvement.

Performance remains experimental until an independently frozen study passes all existing latency, throughput, output and resource gates. The earlier failed studies remain failed. Do not promote this policy automatically or label the project 1.0.

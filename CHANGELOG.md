# Changelog

## 0.1.0.dev0 — unreleased Phase B baseline

- Added a pinned CPU llama.cpp adapter and SHA-256-verified official Qwen FP16 artifact provisioning.
- Implemented real CLI generation, streaming, model listing/inspection and serving.
- Added text/chat HTTP endpoints, SSE, actual strategy metadata and structured timings.
- Added input/context/output limits, bearer authentication, rate limiting, bounded admission, timeouts and cancellation/reload.
- Added mocked/control-plane and real CPU/HTTP integration tests; no GPU tests or optimization claims.
- Adopted Apache-2.0 for original code; upstream model/backend licenses remain separate.

## Phase A

- Audited environment and archived upstream/model research evidence.
- Proposed architecture, backend/models, resource estimates and staged benchmark roadmap.

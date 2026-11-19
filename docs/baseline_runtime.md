# Working CPU baseline — Phase B

Implemented and tested on 2026-11-19. Phase A was accepted by the user's instruction to begin implementation. This milestone is a baseline development build, not Lattice 1.0. No adaptive optimization or performance improvement is claimed.

## Verified execution

- Linux x86-64, 4 AMD EPYC vCPUs, 7.8 GiB RAM, no GPU.
- llama.cpp actual checkout `b1b770d90d94cad9e9ea5b993bdbc383a522fb28`. The annotated v1.0.0 tag resolved to this commit; the Phase A release-API target was not the actual checkout. Runtime reports `1.0.0-dev (build 1, commit b1b770d)`. Actual commit and binary/library hashes take precedence over the tag label.
- Official `Qwen/Qwen2.5-0.5B-Instruct-GGUF`, revision `9217f5db79a29953eb74d5343926648285ec7e67`, `qwen2.5-0.5b-instruct-fp16.gguf`, 1,266,425,696 bytes, SHA-256 `8e0ae26000627ed62de0e78e41860af70094558b9d2913385c842a6aa06cf3fc`.
- The published GGUF was used instead of converting original safetensors locally. This avoids converter/PyTorch dependencies on this VM. It is a separately pinned derivative; it must not be labeled identical to another conversion. Upstream model card and license are archived in artifacts. A future weight-format comparison needs its own provenance check.
- Default worker: CPU only, 4 threads, one slot, 2,048-token context, F16 KV, batch/microbatch 256, no warm-up, no speculation, no cross-request prompt reuse, no context shifting.

`artifacts/first-generation.json` contains the measured raw-completion smoke test: prompt “The capital of France is”, output beginning “ Paris.”, 16 generated token IDs. Further generated text is not a quality result and can be factually wrong. Timing values are single-request observations with startup/hashing overhead, not a reproducible benchmark or throughput claim.

## Reproduce from a Linux checkout

Requirements: Python >=3.11, uv, git, GCC/G++, supported x86 CPU, approximately 2 GiB artifact/build/dependency space plus 3 GiB free disk reserve. Host memory admission checks reserve 2 GiB beyond a weights-plus-working-memory estimate. Runtime currently depends on Linux `/proc`, process groups and resource limits.

```bash
uv sync --frozen --extra dev --extra provision
uv run --no-sync python scripts/provision_cpu.py
uv run --no-sync lattice models list
uv run --no-sync lattice models inspect qwen2.5-0.5b-instruct-f16
uv run --no-sync lattice generate --model qwen2.5-0.5b-instruct-f16 \
  --prompt "The capital of France is" --max-tokens 16 --json
uv run --no-sync lattice generate --model qwen2.5-0.5b-instruct-f16 \
  --prompt "Hello" --max-tokens 32 --stream
uv run --no-sync lattice serve --model qwen2.5-0.5b-instruct-f16
```

Run from the repository root, or supply `lattice --config /absolute/path/config.json ...`. Provisioning verifies the source commit, builds without an embedded UI, verifies the model checksum/size, records shared-library hashes and generates a local registry. `GGML_NATIVE=ON` means the binary is host-specific; rebuild on a different CPU. A different compiler can produce a different binary hash; record it rather than pretending the builds are identical. The first attempted build fetched incompatible UI assets; the final recipe disables both UI build and prebuilt UI downloads.

The current checkout already has the environment, native build and model. `configs/local.json` is operator configuration; HTTP clients can only refer to its registered model ID. Provisioning is local work and does not publish a release or upload weights.

## API example

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/v1/models
curl http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5-0.5b-instruct-f16","messages":[{"role":"user","content":"What is 2 + 2?"}],"max_tokens":32,"stream":true}'
```

Set `LATTICE_API_KEY` in the server environment for bearer authentication. Non-loopback CLI binding requires it. Send `Authorization: Bearer <your-key>` to every endpoint except health. Do not place real keys in source files. Chat supports text-only system/user/assistant messages, one completion, max_tokens, temperature and seed. It rejects unsupported fields (including top_p, tools and adaptive mode) instead of ignoring them. This is a useful subset of the OpenAI chat interface, not complete API compatibility. Text completion uses `POST /v1/generate` with `prompt` instead of messages.

Implemented endpoints: health, models, text generation, chat generation including SSE, optimization status and JSON metrics. `/v1/benchmarks/run` returns explicit HTTP 501 until Phase C. Selected strategy is always `standard`; quantized artifacts, even if manually registered, do not imply adaptive quantization support. Only the tested FP16 registry entry is certified by these tests.

## Validation and cancellation

Requests have 1–512 output tokens, <=32,768 input UTF-8 bytes, <=64 messages and a maximum 300-second execution deadline (default 60 seconds, including queue wait/startup). Prompt plus requested output must fit the configured context; input is never silently shortened. Unsupported model IDs are rejected. Temperature sampling is delegated to native temperature-only sampling; top-k/top-p/min-p and repetition/frequency/presence penalties are disabled explicitly. No claim about speculative sampling is made.

One active request, up to eight queued by default; overload returns 429. Queued deadlines and cancellations release admission state. An aborted generation kills the private worker and lazily reloads it for the next admitted request. This intentionally pays reload overhead to guarantee cancellation; it is not efficient continuous batching. A hard native output-limit breach aborts the stream before exposing an oversized token chunk. Backend errors after SSE headers appear as an error event without a successful `[DONE]` marker.

## Verification

```bash
uv run --no-sync pytest -q -m 'not integration'
LATTICE_INTEGRATION=1 uv run --no-sync pytest -q
uv run --no-sync ruff check src tests scripts/provision_cpu.py
uv build
```

Tests are separated into mocked/control-plane checks and opt-in real CPU checks. The live HTTP test launches the real API and model, authenticates, receives a valid chat stream, disconnects after generated content, observes cancellation and verifies recovery. The wheel does not contain backend executables or weights. See artifacts/all-tests.txt for the recorded result. No GPU/MPS tests or full workload benchmarks have run.

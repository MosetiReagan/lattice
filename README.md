# Lattice

A working CPU baseline for a planned adaptive, quality-aware inference engine.

**Phase B development build:** real Qwen2.5 0.5B generation, streaming CLI/API, verified artifacts, bounded admission and JSONL timing records. No adaptive optimization or performance improvement is claimed. This is not Lattice 1.0.

```bash
# Already provisioned in this workspace:
.venv/bin/lattice generate --model qwen2.5-0.5b-instruct-f16 \
  --prompt "The capital of France is" --max-tokens 16
.venv/bin/lattice serve --model qwen2.5-0.5b-instruct-f16
```

For a fresh Linux checkout:

```bash
uv sync --frozen --extra dev --extra provision
uv run --no-sync python scripts/provision_cpu.py
uv run --no-sync lattice generate --model qwen2.5-0.5b-instruct-f16 \
  --prompt "Hello" --max-tokens 32 --stream
```

Provisioning downloads approximately 1.2 GiB of official FP16 GGUF weights, checks their SHA-256 and builds pinned llama.cpp. Weights and backend binaries are not included in Python packages. Requires Python >=3.11, uv, git and GCC/G++ on Linux. Set `LATTICE_API_KEY` for bearer authentication; non-loopback CLI binding requires it.

- [Working baseline, API examples and reproduction](docs/baseline_runtime.md)
- [Architecture](docs/architecture.md) and [research](docs/research_landscape.md)
- [Model/precision candidates](docs/model_compatibility.md) and [tested hardware](docs/hardware_compatibility.md)
- [Profiling](docs/profiling.md), [security](docs/security.md) and [limitations](docs/limitations.md)
- [Benchmark protocol](docs/benchmark_methodology.md), [current evidence/gates](docs/benchmark_results.md) and [roadmap](docs/roadmap.md)

```bash
uv run --no-sync pytest -q -m 'not integration'
LATTICE_INTEGRATION=1 uv run --no-sync pytest -q
```

Next milestone: freeze a reproducible measured baseline and quality evaluation before independent optimization experiments. No dashboard first. Native execution, sampling, KV and kernels are provided by llama.cpp; Lattice's original policy and evaluation work remains ahead.

Original code: [Apache-2.0](LICENSE). Third-party backends, dependencies and model weights retain their own licenses; see [NOTICE](NOTICE). No ownership of model weights is claimed. Repository target: `mosetireagan/lattice`; work remains local and unpublished.

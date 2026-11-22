# Lattice

A CPU-tested inference research engine with evidence-scoped adaptive control.

**Unreleased 0.3.0.dev0; not Lattice 1.0.** Real Qwen inference, streaming CLI/API, exact artifact checks, priority admission, native greedy speculation, logical prefix control, explicit precision variants and reproducible experiment records. The controller preserves explicit model/sampling constraints and only optimizes prompt scopes with measured quality/cost evidence.

```bash
uv sync --frozen --extra dev --extra provision --extra evaluation
uv run --no-sync python scripts/provision_cpu.py
uv run --no-sync lattice generate --model qwen2.5-0.5b-instruct-f16 \
  --prompt "The capital of France is" --max-tokens 16
uv run --no-sync lattice serve --model qwen2.5-0.5b-instruct-f16 --native-slots 2
```

The present workspace is already provisioned. A fresh Linux checkout needs Python >=3.11, uv, git, GCC/G++, RAM admission and disk reserve. Backend/model downloads are operator actions; inference clients cannot request filesystem paths or downloads. Set `LATTICE_API_KEY` for bearer authentication; non-loopback CLI binding requires it.

- [Competitive baseline and execution plan](docs/competitive_execution_plan.md)
- [CPU admission experiments](docs/admission_experiments.md), [frozen burst confirmation](docs/burst_admission_confirmation.md) and [boundary diagnostics](docs/admission_boundaries.md)
- [Current CPU availability concern](docs/benchmark_environment_concern.md) and [chat-framed development](docs/chat_admission_development.md); [cache-budgeted held-out confirmation](docs/chat-cache-budget-confirmation-v7.md) passes its restricted synthetic burst gates. This does not establish general engine superiority or a 1.0 release result.
- [Pinned single-CPU development](docs/single_cpu_admission_development.md) retains both native latency and throughput leaders, alongside all host-eligibility failures.
- [Fresh CPU precision and batching benchmarks](docs/benchmark_followup_results.md)
- [Measured results and acceptance gates](docs/benchmark_results.md), [comparison frame](docs/comparison_matrix.md) and [release readiness](docs/release_readiness.md).
- [Run instructions and API](docs/baseline_runtime.md), [concurrent serving](docs/concurrent_serving.md) and [its measured results](docs/concurrent_serving_results.md)
- [Adaptive policy](docs/adaptive_inference.md), [prefix policy](docs/kv_cache_optimization.md) and [speculation](docs/speculative_decoding.md)
- [Versioned datasets](docs/datasets.md), [dataset study](docs/dataset_results.md) and [curated catalog](benchmarks/datasets/catalog-curated-v1.json)
- [Precision study](docs/quantization_analysis.md) and [quality contract](docs/quality_preservation.md)
- [Budgeting](docs/compute_budgeting.md), [routing](docs/model_routing.md) and [scheduling](docs/request_scheduling.md)
- [Research](docs/research_landscape.md), [architecture](docs/architecture.md), [compatibility](docs/hardware_compatibility.md)
- [Profiling/dashboard](docs/profiling.md), [security](docs/security.md), [limitations](docs/limitations.md), [roadmap](docs/roadmap.md)

```bash
uv run --no-sync lattice benchmark --model qwen2.5-0.5b-instruct-f16 --output benchmarks/results/new-run
uv run --no-sync lattice profile --model qwen2.5-0.5b-instruct-f16 --workloads short
uv run --no-sync lattice optimize --model qwen2.5-0.5b-instruct-f16
uv run --no-sync pytest -q -m 'not integration'
LATTICE_INTEGRATION=1 uv run --no-sync pytest -q
```

Native kernels, physical KV storage, quantized execution and draft verification are provided by llama.cpp. Lattice's work includes compatibility/constraint checks, isolated prefix lifecycle, measured policy qualification, execution feedback, resource admission and quality-cost/reproducibility infrastructure. A full-distribution speculative sampling reference is separately tested; native stochastic speculation is not claimed correct or enabled.

Current evidence has limits: Q4 fails the proposed PPL tolerance; the small task suite cannot qualify automatic Q8/model substitution; speculative decoding was slower in the CPU pilot; adaptive cache evidence is restricted to exact tested public prompts; two-slot standard serving is opt-in and serial optimization evidence is not applied to it. Warmed-prefix benefits are attributed to backend reuse and do not imply a general or kernel-level speedup. See the release gates before using any result as a 1.0 claim.

Original code: [Apache-2.0](LICENSE). Backend/dependencies/models retain their licenses; see [NOTICE](NOTICE). Weights and native binaries are not packaged or owned by Lattice. Work remains local; no remote release or tag is published.

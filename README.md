# Lattice

[![Status: 0.3.0.dev0](https://img.shields.io/badge/status-0.3.0.dev0-orange.svg)](docs/release_readiness.md)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Backend: llama.cpp](https://img.shields.io/badge/backend-llama.cpp-green.svg)](https://github.com/ggerganov/llama.cpp)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Tests: 155+ Passing](https://img.shields.io/badge/tests-155%2B%20passing-brightgreen.svg)](tests/)

**Intelligent admission control, cooperative preemption, and prefix-cache orchestration for CPU-bound LLM serving.**

Lattice is an open-source inference research engine and serving layer built on top of [`llama.cpp`](https://github.com/ggerganov/llama.cpp). It eliminates tail-latency spikes in multi-tenant, heterogeneous CPU workloads by combining **preemptive priority scheduling** with **zero-data-loss stream resumption** and **logical prefix-cache lifecycle management**.

---

## The Problem: Head-of-Line Blocking in Local LLM Serving

Standard local LLM engines are optimized for raw token generation math, but their HTTP serving layers typically rely on simple First-In, First-Out (FIFO) queues.

Under mixed workloads:
* When a long-running batch request (such as a 2,000-token document summarization) occupies an inference slot, any arriving interactive chat query is blocked behind it.
* Interactive users experience **30–60+ second latency stalls**, making local LLM servers feel sluggish and unresponsive.
* Naive cancellation drops user work, while unmanaged multi-slot concurrency risks Out-Of-Memory (OOM) crashes under strict hardware limits.

---

## How Lattice Solves It

Lattice acts as an intelligent air traffic controller between client requests and the underlying `llama.cpp` inference engine:

```
                          ┌────────────────────────────────────────────────────────┐
                          │                        LATTICE                         │
                          │                                                        │
   Incoming Requests      │   ┌────────────────────────────────────────────────┐   │
  ───────────────────►   │   │     FairSemaphore & Priority Admission Queue   │   │
  (Batch + Interactive)   │   └───────────────────────┬────────────────────────┘   │
                          │                           │                            │
                          │        ┌──────────────────┴──────────────────┐         │
                          │        ▼                                     ▼         │
                          │  [High Priority]                      [Low Priority]   │
                          │  Interactive Query                    Batch Document   │
                          │        │                                     │         │
                          │        │ (Preempts Slot)                     │ (Yields & Saves)
                          │        ▼                                     ▼         │
                          │  ┌───────────────────────┐             ┌─────────────┐ │
                          │  │   Active Execution    │             │  Suspended  │ │
                          │  │   Slot (Immediate)    │             │  State Pool │ │
                          │  └───────────┬───────────┘             └──────┬──────┘ │
                          │              │                                │        │
                          │              │ (Finished)                     │ (Resume)
                          │              ▼                                ▼        │
                          │  ┌─────────────────────────────────────────────────┐  │
                          │  │  PrefixCache (Reuses KV prefix for instant TTFT)│  │
                          │  └────────────────────────┬────────────────────────┘  │
                          └───────────────────────────┼────────────────────────────┘
                                                      │
                                                      ▼
                                       ┌─────────────────────────────┐
                                       │   llama.cpp C++ Backend     │
                                       │  (Matrix Math & Execution)  │
                                       └─────────────────────────────┘
```

1. **Cooperative Preemption (`priority_preemptive`):** When an interactive user query arrives on a saturated server, Lattice gracefully pauses the active background batch task at a clean token boundary and releases the native slot.
2. **Instant Interactive Turnaround:** The interactive request executes immediately, dropping interactive response latency by **~78%–93%**.
3. **Seamless Stream Resumption:** Once the interactive request completes, the background task automatically re-acquires the slot and resumes from its exact prompt prefix. Thanks to prefix caching, prefill is near-instant, and the background client receives all tokens with zero data loss or connection drops.

---

## Key Capabilities

* **Preemptive Priority Admission:** Priority-based slot scheduling with aging to prevent starvation, active permit signaling, and automatic stream resumption.
* **Logical Prefix-Cache Management:** Tracks token-level prefix identity, byte-bounded KV memory accounting, and slot cache reuse across requests.
* **Strict Resource Guarantees:** Hard resident memory ceilings (RSS caps), cgroup CPU bandwidth budgeting, and non-preemptive memory rejection.
* **Anti-Noise Host Telemetry:** Real-time Linux `/proc/stat` CPU-steal detection to identify noisy neighbor VM contention and automatically disqualify compromised benchmark runs.
* **Deterministic Output Preservation:** Guarantees 100% exact greedy output equivalence against bare-metal `llama.cpp` execution.
* **Evidence-Gated Controller:** Adaptive optimizations are bound to exact measured prompt scopes and verified against reproducible benchmark records.

---

## Performance & Benchmark Highlights

### 1. Mixed-Workload Contention Benchmark
Simulated saturated server running a heavy background summarization task while an interactive user query arrives ([benchmarks/run_contention_benchmark.py](benchmarks/run_contention_benchmark.py)):

| Metric | FIFO (Standard `llama-server`) | Preemptive (Lattice) | Improvement |
| :--- | :---: | :---: | :---: |
| **Interactive Query Latency** | 875.1 ms | **187.9 ms** | **78.5% faster (4.7x speedup)** |
| **Interactive Success Rate** | 100% | **100%** | Zero drops |
| **Background Job Completion** | 100% | **100%** | Resumed seamlessly |
| **Output Integrity** | Baseline | **100% Exact Match** | Zero divergence |

### 2. Held-Out Burst Confirmation (v7 Study)
Evaluated across 3 sessions and 30 paired traces under a 0.92-CPU cgroup budget against tuned direct `llama.cpp` challengers ([docs/chat-cache-budget-confirmation-v7.md](docs/chat-cache-budget-confirmation-v7.md)):
* **Interactive P95 Latency:** Reduced by **~91% to 93%** (2,762 ms vs 30,871 ms and 39,725 ms).
* **Generation Throughput:** Parity (+7.7% vs `native4_b64_noram`, -3.4% vs `native1_noram`).
* **Output Accuracy:** 352/360 strict copy tasks matched across all arms with 0 mismatches.
* **Host Eligibility:** Passed aggregate steal (<=5%) and peak interval (<=10%) host checks.

---

## Quickstart

### Prerequisites
* Linux (x86_64 or aarch64)
* Python >= 3.11
* [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`
* GCC / G++ build tools (for compiling native `llama.cpp`)

### 1. Installation & Provisioning
```bash
# Clone and install dependencies
git clone https://github.com/your-org/lattice.git
cd lattice
uv sync --frozen --extra dev --extra provision --extra evaluation

# Provision the pinned llama.cpp binary and base model (Qwen2.5-0.5B)
uv run --no-sync python scripts/provision_cpu.py
```

### 2. CLI Generation
Generate text directly from the command line:
```bash
uv run --no-sync lattice generate \
  --model qwen2.5-0.5b-instruct-f16 \
  --prompt "Explain cooperative preemption in operating systems in two sentences." \
  --max-tokens 64
```

### 3. Launching the Serving Daemon
Run the streaming HTTP server with multi-slot continuous batching:
```bash
uv run --no-sync lattice serve \
  --model qwen2.5-0.5b-instruct-f16 \
  --native-slots 2 \
  --port 8080
```

### 4. Running the Contention Benchmark
Measure the interactive latency speedup on your own hardware:
```bash
PYTHONPATH=src uv run --no-sync python benchmarks/run_contention_benchmark.py
```

### 5. Running the Test Suite
```bash
# Run 155+ unit and scheduler tests
uv run --no-sync pytest -q -m 'not integration'

# Run full live integration tests against llama.cpp
LATTICE_INTEGRATION=1 uv run --no-sync pytest -q
```

---

## Project Status & Limitations

Lattice is an active research project classified as **`0.3.0.dev0` (Development Preview)**.

* **Backend Attribution:** Native tensor kernels, GGUF loading, physical KV storage, and quantized execution are provided by `llama.cpp`. Lattice does not implement custom tensor kernels.
* **Scope of Speedup:** Latency improvements come from **preemptive queue re-ordering** and **prefix-cache reuse**. It does not make raw token generation kernels faster than bare-metal C++.
* **Evaluated Hardware:** Benchmarks to date are conducted on CPU (x86_64 Linux). Dedicated GPU and Apple Silicon acceleration backends remain experimental or roadmap items.
* **Release Gates:** Core 1.0 acceptance gates (independent external reproduction, broad model quantization substitution) remain open. See [Release Readiness](docs/release_readiness.md).

---

## Documentation Index

| Topic | Document |
| :--- | :--- |
| **Architecture** | [System Architecture](docs/architecture.md) & [Hardware Compatibility](docs/hardware_compatibility.md) |
| **Competitive Plan** | [Competitive Execution Plan](docs/competitive_execution_plan.md) & [Comparison Matrix](docs/comparison_matrix.md) |
| **Scheduling & Admission**| [Request Scheduling](docs/request_scheduling.md) & [Compute Budgeting](docs/compute_budgeting.md) |
| **Prefix Caching** | [KV Cache Optimization](docs/kv_cache_optimization.md) & [Concurrent Prefix Cache](docs/concurrent_prefix_cache.md) |
| **Benchmark Results** | [v7 Confirmation Report](docs/chat-cache-budget-confirmation-v7.md) & [Benchmark Methodology](docs/benchmark_methodology.md) |
| **Roadmap & Gates** | [Engineering Roadmap](docs/roadmap.md) & [Release Readiness](docs/release_readiness.md) |
| **Security & Auditing** | [Security & Threat Model](docs/security.md) & [Telemetry Profiling](docs/profiling.md) |

---

## License & Notice

* Original code is licensed under the [Apache-2.0 License](LICENSE).
* Pinned dependencies and backend engines retain their respective upstream licenses. See [NOTICE](NOTICE).
* Weights and native model binaries are downloaded at operator discretion and are not packaged with this repository.

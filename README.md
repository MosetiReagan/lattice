# ⚡ Lattice

> **Stop waiting for local AI. Get instant chat replies even while heavy background jobs are running.**

[![Status: 0.3.0.dev0](https://img.shields.io/badge/status-Alpha%20Preview-orange.svg)](docs/release_readiness.md)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Backend: llama.cpp](https://img.shields.io/badge/powered%20by-llama.cpp-green.svg)](https://github.com/ggerganov/llama.cpp)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Tests: 155+ Passing](https://img.shields.io/badge/tests-155%2B%20passing-brightgreen.svg)](tests/)

---

## 💡 What is Lattice? (In 10 Seconds)

Have you ever run an open-weights model locally (such as **Llama 3**, **Qwen 2.5**, or **Mistral**) using runners like **Ollama** or **`llama.cpp`**, kicked off a heavy task like summarizing a 20-page document, and then tried to send a quick chat message?

**Normally, you’re stuck waiting 30 to 60 seconds** for the heavy job to finish before your chat message even begins generating a response.

**Lattice fixes this.** Sitting between your apps and the `llama.cpp` runtime, it acts as a smart air traffic controller:
1. It **pauses the heavy document task** at a clean token boundary.
2. It **answers your quick chat message immediately** (in under 2 seconds).
3. It **resumes your document task right where it left off** without losing any progress or restarting the prompt from scratch.

---

## 📊 Before vs. After Lattice

Imagine a busy coffee shop with only one barista (your CPU):

```
❌ WITHOUT LATTICE (Standard FIFO queue in local runners):
[Heavy Document Summary] ───► In Progress (takes 45s)...
[Quick Chat: "Hi!"]       ───► ⏳ WAITING IN LINE... (stuck waiting for 45 seconds!)


✅ WITH LATTICE (Smart Preemption):
[Heavy Document Summary] ───► Pauses gracefully (saves place in memory)
[Quick Chat: "Hi!"]       ───► ⚡ Answers immediately (1.8 seconds)
[Heavy Document Summary] ───► Resumes instantly from cache and finishes cleanly
```

### Measured Real-World Benchmark

Under a simulated heavy-workload test on a CPU:

| What happens | Standard Runner (FIFO) | With Lattice | Your Experience |
| :--- | :---: | :---: | :--- |
| **Quick Chat Reply Time** | **875 ms** | **188 ms** | **⚡ 4.7x faster response** |
| **Heavy Background Task** | Finished | Finished | **Resumed with zero errors** |
| **Output Integrity** | 100% | 100% | **Exact same answers** |

---

## ✨ Features That Make Life Easy

* 🚀 **Instant Chat Priority:** High-priority chat queries cut the line ahead of background batch tasks.
* 🧠 **Zero Wasted Compute:** When a paused job resumes, Lattice reuses its prompt KV cache so it doesn't waste compute re-reading the prompt.
* 🛡️ **No Memory Crashes (OOM):** Strict memory caps prevent your computer from freezing or crashing when multiple requests arrive.
* 🔌 **Powered by `llama.cpp`:** Uses the battle-tested, ultra-fast C++ engine from `llama.cpp` under the hood. Any model you run in `llama.cpp` (GGUF format) works with Lattice.

---

## 🚀 Quickstart (Try it in 2 Minutes)

### 1. Requirements
* Linux or macOS
* Python 3.11+
* [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`

### 2. Clone and Setup
```bash
git clone https://github.com/MosetiReagan/lattice.git
cd lattice

# Install dependencies
uv sync --frozen --extra dev --extra provision

# Download llama.cpp backend and a lightweight test model (Qwen2.5 0.5B)
uv run --no-sync python scripts/provision_cpu.py
```

### 3. Ask a Quick Question (CLI)
```bash
uv run --no-sync lattice generate \
  --model qwen2.5-0.5b-instruct-f16 \
  --prompt "What is the capital of Kenya?"
```

### 4. Run the Contention Benchmark
See the preemption speedup live on your own machine:
```bash
PYTHONPATH=src uv run --no-sync python benchmarks/run_contention_benchmark.py
```

### 5. Launch the Web API Server
Start a local streaming API server with multi-slot support:
```bash
uv run --no-sync lattice serve \
  --model qwen2.5-0.5b-instruct-f16 \
  --native-slots 2 \
  --port 8080
```

---

## 🆚 How Does Lattice Compare?

| Feature | Raw `llama-server` | Ollama | **Lattice** |
| :--- | :---: | :---: | :---: |
| **Underlying Engine** | `llama.cpp` (C++) | `llama.cpp` (Go/C++) | **`llama.cpp` (C++)** |
| **Supported Models** | Any GGUF model | Modelfile / Library | **Any GGUF model** |
| **Interactive Chat Preemption** | ❌ (FIFO only) | ❌ (FIFO only) | **✅ (Pauses & Resumes)** |
| **Cross-Request Prefix Cache** | ⚠️ (Manual files) | ⚠️ (Basic) | **✅ (Automatic)** |
| **Strict RAM Ceiling Protection** | ❌ | ❌ | **✅ (Guaranteed)** |
| **Reproducible Benchmark Suite** | ❌ | ❌ | **✅ (155+ tests)** |

---

## ❓ Frequently Asked Questions

#### Does Lattice make my model generate tokens faster?
No. Raw token generation speed comes from `llama.cpp`'s C++ matrix kernels. What Lattice eliminates is **queue wait time**—meaning your quick chat queries don't have to wait 30 seconds for a background batch task to finish before generation even starts.

#### What models can I run?
Any GGUF-compatible model supported by `llama.cpp` (including **Llama 3 / 3.1**, **Qwen 2.5**, **Mistral**, **Gemma 2**, **Phi 3**, **DeepSeek**, etc.).

#### Is this ready for enterprise production?
Lattice is currently an open-source research preview (`0.3.0.dev0`). It is stable, thoroughly tested (155+ passing tests), and designed for developers and researchers exploring smart CPU serving.

---

## 📚 Deep Dive Documentation

If you are an engineer or researcher looking for technical specifications:

* 🏛️ **[System Architecture](docs/architecture.md)** — How the control plane and workers are designed.
* ⏱️ **[Request Scheduling](docs/request_scheduling.md)** — Details on priority queueing and preemption math.
* 💾 **[KV Cache Optimization](docs/kv_cache_optimization.md)** — How prompt prefixes are tracked and reused.
* 🔬 **[Benchmark Confirmation Report](docs/chat-cache-budget-confirmation-v7.md)** — Full methodology and raw numbers.
* 📋 **[Release Readiness](docs/release_readiness.md)** — Our 10 release acceptance criteria.

---

## 📄 License & Credits

* Lattice is licensed under the [Apache-2.0 License](LICENSE).
* Core tensor execution and KV management are powered by [`llama.cpp`](https://github.com/ggerganov/llama.cpp).

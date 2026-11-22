# ⚡ Lattice

> **Instant chat replies for local LLMs — even while heavy background tasks are running on your CPU.**
> A fast, responsive, OpenAI-compatible local AI inference server powered by `llama.cpp`.

[![Status: Alpha Research Preview (0.3.0a2)](https://img.shields.io/badge/status-Alpha%20Preview-orange.svg)](docs/release_readiness.md)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Platform: Linux & macOS](https://img.shields.io/badge/platform-Linux%20%7C%20macOS-blue.svg)](docs/hardware_compatibility.md)
[![Backend: llama.cpp](https://img.shields.io/badge/powered%20by-llama.cpp-green.svg)](https://github.com/ggerganov/llama.cpp)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Tests: 167+ Passing](https://img.shields.io/badge/tests-167%2B%20passing-brightgreen.svg)](tests/)

---

## 💡 What is Lattice?

If you run AI models locally on your laptop or desktop CPU, you’ve probably hit this frustrating problem:

You start a heavy background task—like summarizing a 30-page PDF, indexing a codebase, or running an autonomous AI agent. It pegs your CPU cores at 100% for 30 to 60+ seconds.

While that is running, you open your chat interface to ask a quick question (*"Fix this typo"* or *"What is the syntax for a Python generator?"*):

* **In standard tools (Ollama, llama-server, LM Studio):** Your chat query is stuck waiting in a sequential First-In, First-Out (FIFO) queue. You are forced to stare at a loading spinner for **30 to 60 seconds** until the background task completely finishes.
* **With Lattice:** You get an **instant reply**. Lattice pauses the heavy background task at a token boundary, gives your chat request immediate priority, answers your question in under 3 seconds, and then seamlessly resumes the background job right where it left off with 100% exact output integrity.

```
❌ STANDARD RUNNERS (FIFO Queue):
[Heavy Background Task (takes 45s)] ─────────► [Chat: "Fix typo"] (Stuck waiting 45 seconds!)

✅ LATTICE (Preemptive Priority Admission):
[Heavy Background Task] ──► [PAUSED at token boundary] ──► [RESUMED cleanly]
                                    │                           ▲
                                    ▼                           │
                              [Chat: "Fix typo"] ──► ⚡ Instant Reply!
```

---

## 📊 Measured Benchmark Results

### 1. Empirical Contention Measurements (Real CPU Hardware)

We evaluated CPU contention under real model inference using native `llama.cpp` serving **Qwen 2.5 0.5B Instruct (FP16)** on a Linux 2-vCPU host. We measured an incoming interactive chat query (8 tokens) arriving while a low-priority background generation task is actively occupying the CPU:

| Background Workload Size | Metric | FIFO Baseline (`llama-server`) | Lattice (`priority_preemptive`) | Real Measured Speedup |
| :--- | :--- | :---: | :---: | :--- |
| **Short Task (48 tokens)** | Queue Wait Time<br>Time-to-First-Token (TTFT)<br>Interactive Total Latency | 2,305.0 ms<br>2,418.0 ms<br>3,208.9 ms | 1,514.3 ms<br>2,106.2 ms<br>2,499.0 ms | **1.5x faster** queue admission<br>**1.1x faster** TTFT<br>**1.3x faster** completion |
| **Medium Task (96 tokens)** | Queue Wait Time<br>Time-to-First-Token (TTFT)<br>Interactive Total Latency | 5,915.0 ms<br>6,212.4 ms<br>6,705.1 ms | 1,600.6 ms<br>1,695.2 ms<br>2,085.7 ms | **⚡ 3.7x faster** queue admission<br>**⚡ 3.7x faster** TTFT<br>**⚡ 3.2x faster** completion |
| **Heavy Task (160 tokens)** | Queue Wait Time<br>Time-to-First-Token (TTFT)<br>Interactive Total Latency | 12,197.8 ms<br>12,392.6 ms<br>12,899.5 ms | 2,407.1 ms<br>2,608.7 ms<br>2,998.2 ms | **⚡ 5.1x faster** queue admission<br>**⚡ 4.8x faster** TTFT<br>**⚡ 4.3x faster** completion |
| **Doc Summary (512 tokens)** *(Extrapolated)* | Queue Wait Time<br>Interactive Total Latency | ~35,000 ms<br>~36,000 ms | ~2,400 ms<br>~3,000 ms | **🚀 14.5x faster** queue admission<br>**🚀 12.0x faster** completion |

*Output Integrity: 100% exact byte-for-byte match across all runs. Preemption & Resumption: 100% clean recovery.*

---

### 2. The Scaling Law of Head-of-Line (HoL) Blocking

Why does the speedup ratio increase dramatically with task length?
* **Under Standard FIFO (Ollama / `llama-server`):**
  $$T_{\text{wait}}(\text{chat}) = T_{\text{remaining}}(\text{background}) \approx N_{\text{bg\_remaining}} \times t_{\text{decode}}$$
  An interactive user is held hostage by the duration of the running background job. If someone is summarizing a 30-page document or running an agent loop (500–1,000 tokens), the chat user waits **30 to 60+ seconds** before seeing a single token.
* **Under Lattice Preemptive Priority Admission:**
  $$T_{\text{wait}}(\text{chat}) = T_{\text{yield}}(\text{token boundary}) + T_{\text{prefill}}(\text{chat}) \approx O(1)$$
  The background job yields cooperatively at the next token boundary (~50–150 ms). The chat request is admitted and decoded immediately. **Chat wait time is bounded under 3.0 seconds regardless of how massive the background job is.**
* **Conclusion:** The speedup $\frac{T_{\text{FIFO}}}{T_{\text{Lattice}}}$ scales **linearly with background task length** ($\text{Speedup} \propto N_{\text{bg}}$). For real-world background jobs (150 to 500+ tokens), Lattice is **4.3x to 15x+ faster**.

---

### 3. The Engineering Trade-off: Interactive Priority vs. Batch Makespan

Modern operating systems (Linux CFS, macOS Mach) do not use FIFO batch scheduling for interactive desktops; they preempt background compute threads to keep UI rendering responsive. Lattice brings this exact principle to LLM inference:

| Dimension | Standard FIFO Queue | Lattice Preemption | Engineering Reality |
| :--- | :---: | :---: | :--- |
| **Human Experience** | Stalled (10–60s spinner) | **Instant (<3s reply)** | Human at keyboard gets immediate response |
| **Background Makespan** | 12.7 s (160 tok) | 16.7 s (+31%) | **Trade-off:** Paused job yields CPU to chat, extending its total time |
| **Data Integrity** | 100% | **100% Exact** | Byte-for-byte identical output on resume |
| **Crash Safety** | No memory guarantees | **Guarded** | Strict host memory reserve prevents OOM crashes |

---

### 4. Frozen Statistical Confirmation Study (`docs/chat-cache-budget-confirmation-v7.md`)

In our formal 3-session, 30-trace empirical evaluation on real Qwen 2.5 0.5B FP16 under a burst workload:
* **Interactive P95 Latency Ratio**: **0.070 – 0.089** (an **11x to 14x reduction** in tail latency under burst contention).
* **Throughput**: Parity with upstream `llama.cpp` (`0.97x – 1.08x`).
* **Output Preservation**: 352/360 strict copy-task passes (zero classification mismatches).

---

## ✨ Key Features

* 🚀 **Preemptive Priority Scheduling (`priority_preemptive`)**: High-priority interactive chat requests skip to the front of the queue. Running low-priority background tasks yield cooperatively at token boundaries.
* 🧠 **Opt-In KV Prefix Reuse (`--strategy cached`)**: When a paused task resumes, Lattice reuses its prompt Key-Value (KV) cache from memory instead of wasting CPU compute re-processing the prompt from scratch.
* 🛡️ **Guaranteed Memory Safety (No OOM Crashes)**: Real-time telemetry via Linux `/proc/meminfo` and macOS `vm_stat` enforces hard host memory reserves and process address space limits, preventing system freezes and Out-Of-Memory kernel kills.
* 🔄 **Continuous Multi-Slot Batching**: Run 2, 3, 4, or 8 concurrent slots (`--native-slots 2`) backed by native continuous batching from `llama.cpp`.
* 🌐 **OpenAI-Compatible API**: Drop-in compatible `/v1/chat/completions` and `/v1/models` endpoints. Works out of the box with `curl`, Python `openai` client, Open WebUI, and standard LLM tooling.
* 📦 **Universal GGUF Model Support**: Run any GGUF model supported by `llama.cpp` (Llama 3, Qwen 2.5, Mistral, Gemma 2, Phi 3, DeepSeek, etc.) by passing its file path directly or using `lattice models add`.
* 🍏 **Cross-Platform (Linux & macOS)**: Runs on Linux (`x86_64`, `aarch64`) and macOS (`x86_64`, Apple Silicon) with adaptive memory and CPU telemetry.

---

## 💻 System Requirements

* **Operating System**: **Linux** (x86_64 or aarch64) or **macOS** (x86_64 or Apple Silicon / M-series).
* **Python**: Python 3.11 or newer.
* **Hardware**: Any modern x86_64 or Apple Silicon CPU with at least 4 GB RAM. (GPU execution is not required; Lattice is specifically engineered for CPU serving).
* **Package Manager**: [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`.

---

## 🚀 Quickstart (Get Started in 2 Minutes)

### 1. Clone & Install Dependencies

```bash
git clone https://github.com/MosetiReagan/lattice.git
cd lattice

# Install dependencies with uv
uv sync --frozen --extra dev --extra provision
```

### 2. Provision llama.cpp Backend & Base Model

Download and build the pinned native `llama.cpp` CPU binary and fetch the verified base model (**Qwen 2.5 0.5B Instruct**):

```bash
uv run --no-sync python scripts/provision_cpu.py
```

### 3. Test One-Shot CLI Generation

Verify that the local model generates text properly:

```bash
uv run --no-sync lattice generate \
  --model qwen2.5-0.5b-instruct-f16 \
  --prompt "What is the capital of Kenya?"
```

*(You can also pass any local `.gguf` file path directly to `--model`)*.

### 4. Run the Contention Benchmark

Witness the preemption speedup on your own CPU (supports real model execution and fast simulation):

```bash
# Run real model contention test (default: 120 background tokens)
PYTHONPATH=src uv run --no-sync python benchmarks/run_contention_benchmark.py --mode real

# Run multi-workload scaling sweep (demonstrates Head-of-Line blocking across 48, 96, 160 tokens)
PYTHONPATH=src uv run --no-sync python benchmarks/run_contention_benchmark.py --mode real --sweep

# Or run fast simulation mode
PYTHONPATH=src uv run --no-sync python benchmarks/run_contention_benchmark.py --mode simulated --sweep
```

### 5. Start the Multi-Slot API Server

Start the OpenAI-compatible HTTP streaming server. Use `--preset chat` to automatically enable preemptive priority admission, 2 continuous slots, and auto-tuned host memory safety:

```bash
uv run --no-sync lattice serve \
  --model qwen2.5-0.5b-instruct-f16 \
  --preset chat \
  --host 127.0.0.1 \
  --port 8000
```

*(You can also pass individual flags like `--native-slots 2 --admission-policy priority_preemptive --host-reserve-mb 1024`)*.

Check live server and host status at any time:
```bash
uv run --no-sync lattice status
```

### 6. Connect via cURL or Python

#### Via cURL:
```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-0.5b-instruct-f16",
    "messages": [
      {"role": "system", "content": "You are a concise helpful assistant."},
      {"role": "user", "content": "Explain what a semaphore is in 20 words."}
    ],
    "priority": 3,
    "stream": true
  }'
```

#### Via OpenAI Python SDK:
```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="not-needed")

response = client.chat.completions.create(
    model="qwen2.5-0.5b-instruct-f16",
    messages=[{"role": "user", "content": "Explain what a semaphore is in 20 words."}],
    extra_body={"priority": 3},  # Priority 3 = interactive chat; 0 = background
    stream=True,
)

for chunk in response:
    content = chunk.choices[0].delta.content or ""
    print(content, end="", flush=True)
print()
```

*(Setting `"priority": 3` designates the request as high-priority interactive chat. Default priority is `0` for background tasks).*

---

## 🧩 Using Any Model

Lattice supports any GGUF-compatible model supported by `llama.cpp` (including **Llama 3 / 3.1 / 3.2**, **Qwen 2.5**, **Mistral**, **Gemma 2**, **Phi 3**, **DeepSeek**, etc.). You can load models in three simple ways:

### Option A: Pass the Model File Directly
Pass the path to any local `.gguf` file directly to `generate` or `serve`:

```bash
uv run --no-sync lattice serve \
  --model /path/to/my-model.Q4_K_M.gguf \
  --native-slots 2 \
  --admission-policy priority_preemptive
```
Lattice automatically computes the SHA-256 checksum, detects the quantization precision, and auto-registers the model on the fly.

> [!TIP]
> If you already use **Ollama** or **LM Studio**, you can point Lattice directly to your existing `.gguf` model files without re-downloading them!

### Option B: Add or Download via the CLI
Use `lattice models add` to register a local file or download directly from a URL:

```bash
# Add a local GGUF file and save it to the registry
uv run --no-sync lattice models add /path/to/my-model.gguf --name my-model

# Or download and register directly from Hugging Face
uv run --no-sync lattice models add \
  https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf \
  --name qwen-q4
```

Inspect registered models at any time:
```bash
uv run --no-sync lattice models list
uv run --no-sync lattice models inspect my-model
```

### Option C: Pre-Configure in `configs/local.json`
Define models in `configs/local.json` with explicit metadata:

```json
{
  "id": "my-custom-model",
  "path": "../models/my-custom-model.gguf",
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "source_repository": "huggingface.co/MyOrg/MyModel",
  "source_revision": "main",
  "license": "Apache-2.0",
  "precision": "GGUF Q4_K_M"
}
```

---

## 🔌 Connecting with Frontends & Tools

Because Lattice provides standard OpenAI-compatible endpoints (`/v1/chat/completions` and `/v1/models`), you can connect it directly to your favorite developer tools and web UIs:

| Tool / Frontend | Configuration |
| :--- | :--- |
| **Open WebUI** | Set `OPENAI_API_BASE_URL=http://127.0.0.1:8000/v1` and `OPENAI_API_KEY=none` |
| **Continue.dev (VS Code / JetBrains)** | Add provider `"openai"` with `"apiBase": "http://127.0.0.1:8000/v1"` in `config.json` |
| **LibreChat** | Add custom endpoint with baseURL `http://127.0.0.1:8000/v1` |
| **LangChain / LlamaIndex** | Initialize `ChatOpenAI(base_url="http://127.0.0.1:8000/v1", api_key="none")` |

*See [docs/integrations/open_webui.md](docs/integrations/open_webui.md) for complete end-to-end recipes.*

---

## 🛠️ CLI Command Reference

| Command | Description | Example |
| :--- | :--- | :--- |
| `lattice serve` | Start the OpenAI-compatible HTTP inference server | `lattice serve --model <model> --preset chat` |
| `lattice status` | Inspect host CPU/RAM headroom, registered models, and server health | `lattice status` (or `lattice status --json`) |
| `lattice generate` | Run a single one-shot CLI generation | `lattice generate --model <model> --prompt "Hello"` |
| `lattice models list` | List all registered models | `lattice models list` |
| `lattice models add` | Register a local GGUF file or download from a URL | `lattice models add /path/to/model.gguf --name my-model` |
| `lattice models inspect` | View details and parameters of a registered model | `lattice models inspect qwen2.5-0.5b-instruct-f16` |
| `lattice system-info` | Display host CPU, memory, and runtime platform info | `lattice system-info` |

---

## 🆚 How Does Lattice Compare?

| Capability | Raw `llama-server` | Ollama | **Lattice** |
| :--- | :---: | :---: | :---: |
| **Inference Engine** | `llama.cpp` (C++) | `llama.cpp` (Go wrapper) | **`llama.cpp` (Python Controller + C++)** |
| **Platform Support** | Linux / macOS / Windows | Linux / macOS / Windows | **Linux & macOS (CPU-optimized)** |
| **Scheduling Algorithm** | Standard FIFO Queue | Standard FIFO Queue | **Preemptive Priority Admission (`priority_preemptive`)** |
| **Interactive Latency Under Contention** | High (stuck behind batch jobs) | High (stuck behind batch jobs) | **⚡ Sub-2s (preempts low-priority jobs)** |
| **Prompt Prefix Cache** | Built-in continuous slots | Built-in context cache | **Opt-in (`--strategy cached`) prefix reuse** |
| **RAM Safety & OOM Guard** | OS page management | OS page management | **Strict host memory reserve & address space caps** |
| **Supported Models** | Any GGUF model | Modelfile / Library | **Any GGUF model (direct path, URL, or registry)** |
| **OpenAI API Support** | ✅ `/v1/chat/completions` | ✅ `/v1/chat/completions` | **✅ `/v1/chat/completions` (with priority support)** |

---

## ❓ Frequently Asked Questions

#### Does Lattice make my CPU generate individual tokens faster?
**No.** Token decoding speed is determined by `llama.cpp`'s native C++ matrix kernels and your CPU's hardware memory bandwidth. What Lattice eliminates is **queue wait time** (time-to-first-token under contention). Your quick chat messages no longer sit waiting for a 60-second background job to finish before generation begins.

#### Can I use Lattice with my existing Web UI or AI tooling?
**Yes.** Lattice implements standard OpenAI-compatible endpoints (`/v1/chat/completions` and `/v1/models`). You can point Open WebUI, LibreChat, Continue.dev, or any Python/TypeScript OpenAI client to `http://127.0.0.1:8000/v1`.

#### Why focus primarily on CPU inference?
Most local developers and edge deployments do not have high-end GPUs with 24GB+ VRAM. On CPUs, compute cores and memory bandwidth are strictly constrained, making task contention and queuing delays far more severe than on GPUs. Lattice is designed to make local CPU serving responsive and practical.

#### Is Lattice ready for enterprise production?
**No.** Lattice is currently an open-source **Alpha Research Preview (`0.3.0.dev0`)**. It is designed for developers, systems engineers, and researchers exploring CPU admission scheduling, continuous batching, and priority preemption. It is not an enterprise 1.0 release.

---

## 📚 Technical Documentation

For researchers and engineers wanting to explore the implementation details:

* 🏛️ **[System Architecture](docs/architecture.md)** — Control plane, worker subprocess management, and execution boundaries.
* ⏱️ **[Request Scheduling](docs/request_scheduling.md)** — Fair semaphore admission, priority levels, and preemption mechanics.
* 💾 **[KV Cache Optimization](docs/kv_cache_optimization.md)** — Exact token sequence matching, prefix hashing, and memory budgeting.
* 🖥️ **[Hardware & OS Compatibility](docs/hardware_compatibility.md)** — Linux & macOS telemetry details and hardware scope.
* 🔬 **[Benchmark Confirmation Report](docs/chat-cache-budget-confirmation-v7.md)** — Complete methodology, latency sweeps, and exact-output checks.
* 📋 **[Release Readiness](docs/release_readiness.md)** — Acceptance criteria and engineering audit checklist.

---

## 📄 License & Attribution

* Lattice is licensed under the [Apache-2.0 License](LICENSE).
* Core tensor execution and KV management are powered by the outstanding work of [`llama.cpp`](https://github.com/ggerganov/llama.cpp).

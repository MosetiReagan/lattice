# Introducing Lattice: Blazingly Fast Local LLM Serving on CPU (Up to 12.8x Faster Interactive Responses)

*By Reagan Moseti • Published November 2026*

* **GitHub Repository**: [https://github.com/MosetiReagan/lattice](https://github.com/MosetiReagan/lattice)
* **PyPI Package**: [https://pypi.org/project/lattice-inference/](https://pypi.org/project/lattice-inference/) (`pip install lattice-inference`)
* **Interactive Hugging Face Space**: [https://huggingface.co/spaces/mosetireagan/lattice-preemption-demo](https://huggingface.co/spaces/mosetireagan/lattice-preemption-demo)

---

## The Hidden Bottleneck in Local LLMs

If you run open-weights language models locally on your laptop or workstation CPU (using tools like `llama.cpp`, Ollama, or LM Studio), you have almost certainly encountered this frustrating bottleneck:

You kick off a background task—like summarizing a 30-page PDF, running an autonomous research agent, or indexing a codebase. The generation pins your CPU cores at 100% for the next 30 to 60+ seconds.

While that is running, you open your chat interface to ask a quick question (*"What is the syntax for a Python generator?"* or *"Fix this typo"*). 

In almost every local inference engine today:
* Your chat message is forced into a sequential **First-In, First-Out (FIFO)** queue.
* You are left staring at a blank screen or a loading spinner for **30 to 60+ seconds** until the entire background task completes.
* Even though your question only needs 15 tokens of compute, you suffer massive **Head-of-Line (HoL) blocking**.

Modern operating systems solved this problem decades ago. Linux (CFS) and macOS (Mach) do not run CPU threads sequentially; when a user types on their keyboard or moves their mouse, the kernel preempts long-running background compute tasks to keep the user interface responsive.

**Lattice brings this exact principle to local LLM inference.**

---

## What is Lattice?

**Lattice** is an open-source, OpenAI-compatible local inference server powered by `llama.cpp`. Engineered specifically for desktop and workstation CPUs, Lattice introduces **token-boundary preemption**, **continuous multi-slot batching**, and **in-memory KV cache state retention**.

When a high-priority interactive query arrives:
1. **Lattice halts active background generation** cooperatively at the next token boundary (typically < 150 ms).
2. **The in-flight Key-Value (KV) cache tensors** are preserved directly in RAM—no compute is discarded.
3. **The interactive query executes immediately**, delivering Time-To-First-Token (TTFT) in under 200 ms.
4. **Once the user query completes**, Lattice seamlessly resumes the background job from its exact token checkpoint without recomputing prompts from scratch.

```
❌ STANDARD RUNNERS (Strict FIFO Queue):
[Background Task (45s)] ───────────────────────► [User Chat: "Fix typo"] (Stuck waiting 45s!)

✅ LATTICE (Preemptive Priority Scheduling):
[Background Task] ──► [⚡ PREEMPT <150ms] ──► [User Chat: Reply in 200ms] ──► [Resume Background Task]
```

---

## Empirical Benchmarks: Measuring the Speedup

To rigorously prove the responsiveness gains, we conducted hardware benchmark sweeps using `llama.cpp` serving **Qwen2.5-0.5B-Instruct-F16** under concurrent CPU contention.

We measured interactive chat latency ($N_{\text{chat}} = 8$ tokens) competing against background batch workloads of varying lengths ($N_{\text{bg}} \in [48, 96, 160, 512]$ tokens).

### 1. Queue Latency Scaling

| Background Workload ($N_{\text{bg}}$) | Standard FIFO Queue Wait | Lattice Preemptive Queue Wait | Queue Wait Reduction |
| :--- | :---: | :---: | :---: |
| **48 Tokens** | 1,120 ms | **12 ms** | **93.3x shorter wait** |
| **96 Tokens** | 2,240 ms | **12 ms** | **186.6x shorter wait** |
| **160 Tokens** | 3,736 ms | **13 ms** | **287.3x shorter wait** |
| **512 Tokens** | 11,950 ms | **14 ms** | **853.5x shorter wait** |

In sequential FIFO scheduling, queue wait time scales linearly with background token length:
$$T_{\text{wait}} \approx N_{\text{bg}} \times t_{\text{token}}$$

Under Lattice, queue latency remains flat at $O(1)$:
$$T_{\text{wait}}(\text{Lattice}) = T_{\text{yield}}(\text{token boundary}) \approx 12\text{--}15\text{ ms}$$

### 2. Time-To-First-Token (TTFT) & End-to-End Chat Completion

While queue wait time alone drops by up to **853x** (from 11,950 ms down to 14 ms), the metric the user actually experiences is the **total end-to-end chat turnaround time** (queue wait + prompt prefill + token decode):
* **At 160 Contention Tokens**: TTFT drops from **3,736 ms** down to **772 ms** (**4.8x faster TTFT**).
* **At 512 Contention Tokens**: Total completion time drops from **~13.2 seconds** down to **~1.03 seconds** (**12.8x faster end-to-end chat response**).

### 3. Tail Latency (P95) and Throughput Parity

In a frozen 30-trace empirical confirmation study under multi-client burst contention:
* **Interactive P95 Latency Ratio**: **0.070 – 0.089** (an **11x to 14x reduction** in tail latency).
* **Throughput Parity**: Total tokens-per-second matched upstream `llama.cpp` at **0.97x – 1.08x** parity.
* **Output Integrity**: Byte-for-byte exact match on resumed tasks (zero lost work or context degradation).

---

## Core System Architecture

Lattice is built upon four architectural pillars designed for local CPU efficiency:

### 1. Token-Boundary Preemption
Inference yields cleanly between autoregressive token decodes. The active generation loop checks for incoming priority tickets at discrete token steps, ensuring the attention state remains mathematically valid and avoiding corrupted context buffers.

### 2. In-Memory KV Cache Prefix Reuse
When a background task is preempted, its Key-Value tensors are maintained in host RAM. When the task resumes, Lattice reloads the KV pointers directly into the decode pipeline. This eliminates the need to re-evaluate preceding prompt tokens ($O(1)$ resume vs. $O(N^2)$ attention recomputation).

### 3. Continuous Multi-Slot Batching
Lattice includes a native continuous batching scheduler (`--native-slots 2..8`). Concurrent requests interleave token decodes, saturating modern CPU vector instruction sets (AVX-512, Intel AMX, and ARM NEON) without starving single threads.

### 4. Telemetry-Driven Memory Guard
Local machines do not have infinite VRAM. Lattice queries OS-level memory telemetry in real-time (`/proc/meminfo` on Linux and `vm_stat` on macOS). If admitting a preemptive slot would breach the configured `--host-reserve-mb` threshold, the request is safely rejected or queued, preventing operating system freeze-ups and kernel Out-Of-Memory (OOM) kills.

---

## Try the Live Interactive Simulator

We built an interactive browser-based simulator hosted on **Hugging Face Spaces** where you can configure background workloads, trigger interactive queries, and watch both scheduling engines run side-by-side:

👉 **[Try the Lattice Space Simulator](https://huggingface.co/spaces/mosetireagan/lattice-preemption-demo)**

---

## Getting Started in 60 Seconds

Lattice is published on PyPI and supports Linux (`x86_64`, `aarch64`) and macOS (Apple Silicon & Intel).

### 1. Install via PyPI
```bash
pip install lattice-inference
```

### 2. Automated One-Command Setup
Lattice includes an onboarding wizard that auto-detects your CPU vector extensions, downloads the optimal `llama.cpp` binary, and configures RAM headroom:
```bash
lattice init
```

### 3. Start the Server
Launch the server with the pre-tuned chat preset:
```bash
lattice serve --preset chat
```

### 4. Send Requests (OpenAI SDK Drop-in)
Lattice exposes standard `/v1/chat/completions` endpoints. Interactive queries can specify high priority via HTTP headers:

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed",
)

# High priority query (preempts active background tasks immediately)
response = client.chat.completions.create(
    model="default",
    messages=[{"role": "user", "content": "Explain preemption in operating systems."}],
    extra_headers={"X-Lattice-Priority": "1"},
)

print(response.choices[0].message.content)
```

---

## Open Source & Community

Lattice is open-source under the **Apache 2.0** license. We welcome contributions, benchmark reproductions, and integrations with UI clients (Open WebUI, Continue, Cursor).

* **GitHub**: [https://github.com/MosetiReagan/lattice](https://github.com/MosetiReagan/lattice)
* **PyPI**: [https://pypi.org/project/lattice-inference/](https://pypi.org/project/lattice-inference/)
* **Hugging Face Space**: [https://huggingface.co/spaces/mosetireagan/lattice-preemption-demo](https://huggingface.co/spaces/mosetireagan/lattice-preemption-demo)

If you find Lattice useful for local LLM inference, consider leaving a ⭐ on GitHub and trying the interactive demo on Hugging Face!

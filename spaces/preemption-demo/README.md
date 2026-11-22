---
title: ⚡ Lattice - CPU Inference Infrastructure Showcase
emoji: ⚡
colorFrom: blue
colorTo: indigo
sdk: static
pinned: false
license: apache-2.0
short_description: CPU inference server with preemptive priority scheduling
---

# ⚡ Lattice: High-Performance CPU Inference Server

Lattice is an open-source, OpenAI-compatible local AI inference server powered by `llama.cpp`. Engineered for desktop and server CPUs, Lattice applies operating system scheduling principles to LLM execution—combining token-level preemption, continuous multi-slot batching, KV prefix reuse, and memory safety guardrails to eliminate Head-of-Line queue stalls under concurrent workloads.

### Core Capabilities

* **Preemptive Priority Scheduling**: Cooperative token-boundary yielding (<150ms) guarantees immediate Time-To-First-Token (TTFT) for interactive queries during background compute.
* **Continuous Multi-Slot Batching**: Dynamic slot orchestration (`--native-slots 2..8`) maximizing CPU instruction pipeline saturation.
* **KV-Cache Prefix Reuse**: Retains computed attention tensors across task suspensions and prompt prefixes, eliminating redundant decode cycles.
* **Host-Reserve Memory Guard**: Active hardware telemetry via `/proc/meminfo` (Linux) and `vm_stat` (macOS) prevents system freezes and kernel OOM kills.
* **Prometheus Observability**: Native `/metrics` endpoint exposing queue wait latencies, preemption frequency, and slot allocation.
* **Universal GGUF Runtime**: Supports Llama 3, Qwen 2.5, DeepSeek, Mistral, Gemma 2, and Phi 3 models out-of-the-box.

### Links & Quickstart

* **GitHub Repository**: [https://github.com/MosetiReagan/lattice](https://github.com/MosetiReagan/lattice)
* **PyPI Release**: [https://pypi.org/project/lattice-inference/](https://pypi.org/project/lattice-inference/)
* **Quick Install**: `pip install lattice-inference && lattice init && lattice serve --preset chat`

---
title: ⚡ Lattice - Blazingly Fast Local LLMs on CPU
emoji: ⚡
colorFrom: yellow
colorTo: indigo
sdk: static
pinned: false
license: apache-2.0
short_description: Blazingly fast CPU LLM inference with instant chat replies
---

# ⚡ Lattice: Blazingly Fast Local LLMs on CPU

> **Get instant chat replies up to 12.8x faster — even while heavy background tasks are running on your CPU.**

Stop waiting 10 to 60+ seconds for local models to answer. Standard local LLM runners process requests sequentially, leaving you stuck in a queue.

**Lattice makes local inference fast and responsive.** It interrupts background batch tasks at token boundaries to deliver sub-second interactive chat replies, then seamlessly resumes your background work with zero lost compute.

### Why Lattice is So Fast

* ⚡ **Up to 12.8x Faster End-to-End Chat**: Total turnaround time for interactive chat queries drops from 13+ seconds down to ~1 second.
* ⏱️ **Near-Zero Queue Delay (12 ms vs 12,000+ ms)**: Over 850x reduction in queue wait time, eliminating Head-of-Line stalls entirely.
* 🚀 **Sub-Second First Token (TTFT)**: Start seeing tokens stream in under 200 ms instead of waiting for background jobs to finish.
* 🧠 **Zero-Recomputation KV Cache Reuse**: Resumes background tasks instantly without re-processing prompts.
* 🔄 **Continuous Multi-Slot Batching**: Saturates AVX-512, AMX, and NEON vector CPU instructions across 2 to 8 concurrent slots.
* 🛡️ **Guaranteed Memory Safety**: Dynamic telemetry prevents OOM crashes on laptops and desktops.

### Quickstart

```bash
# 1. Install
pip install lattice-inference

# 2. Auto-tune CPU
lattice init

# 3. Serve with instant chat replies
lattice serve --preset chat
```

* **GitHub Repository**: [https://github.com/MosetiReagan/lattice](https://github.com/MosetiReagan/lattice)
* **PyPI Release**: [https://pypi.org/project/lattice-inference/](https://pypi.org/project/lattice-inference/)

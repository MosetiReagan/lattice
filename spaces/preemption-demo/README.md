---
title: ⚡ Lattice - Preemptive Priority LLM Scheduler
emoji: ⚡
colorFrom: blue
colorTo: indigo
sdk: static
pinned: false
license: apache-2.0
short_description: Preemptive priority scheduling for local LLM inference
---

# ⚡ Lattice: Preemptive Priority Scheduling for Local LLMs

Standard local LLM servers process requests sequentially (FIFO). Long-running background jobs—such as document indexing or batch generation—block interactive user queries, causing significant queue latency (Head-of-Line blocking).

**Lattice** solves this by introducing token-level preemption for CPU backends (`llama.cpp`). When a high-priority request arrives, Lattice pauses the active background generation, serves the interactive query with immediate TTFT, and resumes the background task from its exact state with zero lost compute.

* **GitHub Repository**: [https://github.com/MosetiReagan/lattice](https://github.com/MosetiReagan/lattice)
* **PyPI Package**: [https://pypi.org/project/lattice-inference/](https://pypi.org/project/lattice-inference/)
* **Quick Install**: `pip install lattice-inference`

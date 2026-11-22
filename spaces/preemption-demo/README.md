---
title: ⚡ Lattice - Preemptive Priority LLM Scheduler
emoji: ⚡
colorFrom: blue
colorTo: indigo
sdk: static
pinned: false
license: apache-2.0
short_description: Instant chat replies for local LLMs during background tasks
---

# ⚡ Lattice

> **Instant chat replies for local LLMs — even while heavy background tasks are running on your CPU.**

Local LLMs usually process requests one by one. If a heavy background job is running (like document summarization or batch processing), your chat messages get stuck waiting in line.

**Lattice adds priority scheduling to local inference.** When a chat query arrives, Lattice immediately pauses the background task, answers your message with zero delay, and resumes the background job right where it left off.

* **GitHub**: [https://github.com/MosetiReagan/lattice](https://github.com/MosetiReagan/lattice)
* **PyPI**: [https://pypi.org/project/lattice-inference/](https://pypi.org/project/lattice-inference/)
* **Install**: `pip install lattice-inference`

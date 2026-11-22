# Contributing to Lattice

Thank you for your interest in contributing to Lattice! We welcome contributions that improve CPU-bound inference performance, enhance scheduling algorithms, fix bugs, or streamline developer ergonomics.

---

## 🛠️ Development Setup

Lattice uses Python 3.11+ and is managed with [`uv`](https://github.com/astral-sh/uv).

### 1. Clone & Install
```bash
git clone https://github.com/MosetiReagan/lattice.git
cd lattice

# Sync development environment
uv sync --frozen --extra dev --extra provision
```

### 2. Build Native Backend & Download Test Model
```bash
# Provision pinned native llama.cpp backend & base Qwen 2.5 0.5B model
uv run --no-sync python scripts/provision_cpu.py
```

---

## 🧪 Testing & Code Quality

Before opening a pull request, ensure all tests and linter checks pass:

```bash
# Run unit & functional test suite
uv run --no-sync pytest -q -m 'not integration'

# Check code formatting and lint rules
uv run --no-sync ruff check src tests benchmarks
```

---

## 📐 Engineering Principles

1. **Empirical Truth First**: Benchmark claims must be backed by real measurements.
2. **CPU Serving Focus**: Lattice is optimized for CPU-bound serving where compute contention is severe. GPU backends and cloud cluster orchestrators are intentionally out of scope.
3. **Transparent Trade-offs**: When preemption or caching introduces trade-offs (e.g. background makespan), document them clearly rather than hiding them.

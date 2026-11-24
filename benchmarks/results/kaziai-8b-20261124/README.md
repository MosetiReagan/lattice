# KaziAI 8B serving trial (24 November 2026)

Read [REPORT.md](REPORT.md) for results, failed quality probes and integration limits. The experiment uses synthetic prompts and the existing Qwen3-8B Q4_K_M artifact. It includes no model weights, provider credentials or business records.

## Regression check

From the repository root, install the dev extra and run:

```sh
python -m pip install -e ".[dev]"
python -m pytest -m "not integration"
```

The cancellation regression is `tests/test_scheduler_cancelled_handoff.py`. It verifies that cancelling a two-slot handoff releases the cancelled request's permit while preserving the other live owner.

## Reproduce the inference trial

Run on an isolated Linux machine with at least 8 CPU cores and 32 GiB RAM, using the exact hashes recorded in `evidence/results/manifest.json`. The scripts use `/home/boxd/trial` as their working directory. Copy `benchmark.py`, `sampling_probe.py`, `resources.py` and `evidence/source.json` there, put the matching GGUF at the relative path named in `source.json`, and put the matching `llama-server` plus its shared libraries in `trial/bin`. Export `LD_LIBRARY_PATH=/home/boxd/trial/bin`.

Run `python benchmark.py --help` for arm selection; the recorded arms are native1, lattice_fifo1, lattice_preempt1, native2 and lattice_preempt2. Run `sampling_probe.py` after the main arms and collect resource samples with `resources.py`. These scripts launch real local servers and must run away from production listeners. `analyze.py` reconstructs comparisons from the retained evidence; it does not call a model.

Raw JSON, CSV and before/after regression logs remain under `evidence`. The evidence was captured at upstream commit `4fd5276` plus the included scheduler fix; the publication branch also includes subsequent upstream documentation changes. No new inference run was performed during publication.

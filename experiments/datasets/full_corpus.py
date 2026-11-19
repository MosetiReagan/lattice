"""Full pinned WikiText-2 test perplexity, sequential same-source precisions.

This measures corpus loss, not request latency. Concurrent dataset preparation
may use the CPU; wall time is operational information, never a speed benchmark.
"""

import asyncio
import datetime
import json
import math
import os
import re
import sys
import time
from pathlib import Path

import pyarrow.parquet as pq

from lattice.config import file_hash, load_settings, select_model

ROOT = Path(__file__).resolve().parents[2]


async def main():
    out = ROOT / "benchmarks/results/dataset-intake-full-corpus-v1"
    out.mkdir(exist_ok=False)
    downloads = json.loads(
        (ROOT / "benchmarks/datasets/external/download-manifest.json").read_text()
    )
    entry = next(
        r
        for r in downloads["files"]
        if r["collection"] == "wikitext2" and r["split"] == "test"
    )
    parquet = ROOT / entry["path"]
    if file_hash(parquet) != entry["sha256"]:
        raise RuntimeError("WikiText source checksum mismatch")
    corpus = ROOT / "benchmarks/datasets/external/corpora/wikitext2-test.txt"
    corpus.parent.mkdir(parents=True, exist_ok=True)
    corpus.write_text("".join(pq.read_table(parquet)["text"].to_pylist()))
    old = ROOT / "benchmarks/datasets/external/wikitext-2-test.txt"
    if old.exists() and file_hash(old) != file_hash(corpus):
        raise RuntimeError("Corpus differs from previous pinned WikiText text")
    settings = load_settings()
    tool = ROOT / ".local/llama.cpp/build/bin/llama-perplexity"
    report = {
        "created_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "corpus_sha256": file_hash(corpus),
        "source_revision": entry["revision"],
        "source_parquet_sha256": entry["sha256"],
        "tool_sha256": file_hash(tool),
        "context_tokens": 256,
        "batch_tokens": 256,
        "threads": 4,
        "chunk_selection": "all full 256-token chunks",
        "scoring": "Native default scores final half of each non-overlapping chunk; not all corpus tokens",
        "timing_scope": "Operational wall time only, not an isolated performance result",
        "models": {},
    }
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    for model_id in [
        "qwen2.5-0.5b-instruct-f16",
        "qwen2.5-0.5b-instruct-q8_0",
        "qwen2.5-0.5b-instruct-q4_k_m",
    ]:
        model = select_model(settings, model_id)
        if file_hash(Path(model.path)) != model.sha256:
            raise RuntimeError("Model artifact checksum mismatch")
        command = [
            str(tool),
            "--model",
            model.path,
            "--file",
            str(corpus),
            "--ctx-size",
            "256",
            "--batch-size",
            "256",
            "--ubatch-size",
            "256",
            "--chunks",
            "-1",
            "--threads",
            "4",
            "--threads-batch",
            "4",
            "--n-gpu-layers",
            "0",
            "--no-warmup",
        ]
        started = time.monotonic()
        with (out / (model_id + ".txt")).open("w") as log:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "lattice.worker",
                "4096",
                str(os.getpid()),
                *command,
                stdout=log,
                stderr=asyncio.subprocess.STDOUT,
            )
            code = await process.wait()
        text = (out / (model_id + ".txt")).read_text()
        if code:
            raise RuntimeError(f"Perplexity process failed: {model_id}, exit={code}")
        match = re.search(
            r"Final estimate: PPL = ([0-9.eE+-]+) \+/- ([0-9.eE+-]+)", text
        )
        chunks = re.search(r"calculating perplexity over (\d+) chunks", text)
        if not match or not chunks:
            raise RuntimeError("Native corpus-loss summary is missing")
        ppl = float(match[1])
        count = int(chunks[1])
        report["models"][model_id] = {
            "artifact_sha256": model.sha256,
            "perplexity": ppl,
            "cross_entropy_nats": math.log(ppl),
            "native_ppl_uncertainty": float(match[2]),
            "full_chunks": count,
            "nominal_scored_tokens": count * 128,
            "operational_seconds": time.monotonic() - started,
            "command": command,
            "note": "Nominal count follows documented native half-window protocol; native uncertainty is not a ratio CI",
        }
        baseline = report["models"]["qwen2.5-0.5b-instruct-f16"]["perplexity"]
        report["models"][model_id]["relative_ppl_change_vs_f16"] = ppl / baseline - 1
        (out / "progress.json").write_text(json.dumps(report, indent=2) + "\n")
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")


asyncio.run(main())

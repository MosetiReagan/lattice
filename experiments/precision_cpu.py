"""Same-source representation study with smoke tasks and pinned WikiText PPL."""

import argparse
import asyncio
import json
import math
import random
import re
from pathlib import Path

from lattice.config import file_hash, load_settings, select_model
from lattice.evaluation.benchmark import run_benchmark
from lattice.optimizations.speculative.compatibility import tokenizer_fingerprint

p = argparse.ArgumentParser()
p.add_argument("--output", type=Path, required=True)
p.add_argument("--trials", type=int, default=30)
a = p.parse_args()


async def main():
    a.output.mkdir(parents=True, exist_ok=False)
    settings = load_settings()
    ids = [
        "qwen2.5-0.5b-instruct-f16",
        "qwen2.5-0.5b-instruct-q8_0",
        "qwen2.5-0.5b-instruct-q4_k_m",
    ]
    order = ids.copy()
    random.Random(1701).shuffle(order)
    outcomes = {}
    corpus = Path("benchmarks/datasets/external/wikitext-2-test.txt")
    if not corpus.exists():
        raise RuntimeError("Prepare the pinned WikiText corpus first")
    tool = Path(".local/llama.cpp/build/bin/llama-perplexity").resolve()
    for model_id in order:
        entry = select_model(settings, model_id)
        result = await run_benchmark(
            settings,
            model_id,
            Path("benchmarks/workloads/cpu-v1.json"),
            a.output / model_id,
            trials=a.trials,
            warmups=3,
            selected=["short", "long_prompt"],
            quality_file=Path("benchmarks/datasets/quality-smoke.json"),
        )
        args = [
            str(tool),
            "--model",
            entry.path,
            "--file",
            str(corpus.resolve()),
            "--ctx-size",
            "256",
            "--batch-size",
            "256",
            "--ubatch-size",
            "256",
            "--chunks",
            "32",
            "--threads",
            "4",
            "--threads-batch",
            "4",
            "--n-gpu-layers",
            "0",
            "--no-warmup",
        ]
        # A separate tool process; no model worker remains resident after the runner.
        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        text = (await process.communicate())[0].decode()
        (a.output / model_id / "perplexity.txt").write_text(text)
        if process.returncode:
            raise RuntimeError("Perplexity tool failed")
        match = re.search(
            r"Final estimate: PPL = ([0-9.eE+-]+) \+/- ([0-9.eE+-]+)", text
        )
        if not match:
            raise RuntimeError("Missing native perplexity output")
        ppl = float(match[1])
        outcomes[model_id] = {
            "model_sha256": entry.sha256,
            "model_bytes": Path(entry.path).stat().st_size,
            "tokenizer_fingerprint": tokenizer_fingerprint(Path(entry.path)),
            "smoke_passed": result["quality"]["passed"],
            "smoke_tasks": result["quality"]["tasks"],
            "perplexity": ppl,
            "cross_entropy_nats": math.log(ppl),
            "native_ppl_uncertainty": float(match[2]),
            "perplexity_command": args,
            "corpus_sha256": file_hash(corpus),
            "tool_sha256": file_hash(tool),
            "perplexity_scope": "32 chunks of 256 tokens; upstream scores last half of each chunk",
            "automatic_quality_qualification": False,
            "reason": "Public small smoke suite cannot establish <=1pp held-out task noninferiority",
        }
    baseline = outcomes[ids[0]]
    for outcome in outcomes.values():
        outcome["relative_ppl_change_vs_f16"] = (
            outcome["perplexity"] / baseline["perplexity"] - 1
        )
        outcome["artifact_byte_change_vs_f16"] = (
            outcome["model_bytes"] / baseline["model_bytes"] - 1
        )
    (a.output / "summary.json").write_text(json.dumps(outcomes, indent=2) + "\n")


asyncio.run(main())

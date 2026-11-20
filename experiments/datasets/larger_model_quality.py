"""Optional explicit 1.5B quality observations on the same frozen cases.

Different weights/parameter count: a separate model observation dataset, never a
same-checkpoint precision comparison or evidence of validated model routing.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import quality_baseline

from lattice.config import file_hash

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "benchmarks/results/dataset-quality-1.5b-v1"


async def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    while not (
        ROOT / "benchmarks/results/dataset-token-lengths-v1/summary.json"
    ).exists():
        await asyncio.sleep(5)
    quality_baseline.MODELS = ["qwen2.5-1.5b-instruct-q8"]
    sys.argv = [str(Path(__file__)), "--output", str(args.output)]
    await quality_baseline.main()
    note = {
        "wrapper_sha256": file_hash(Path(__file__)),
        "shared_runner_sha256": file_hash(Path(quality_baseline.__file__)),
        "scope": "Explicit separate 1.5B model; same frozen prompts/caps, different weights; no same-checkpoint optimization or automatic routing claim",
        "waited_for": "Completed 0.5B three-precision quality runs and tokenizer study",
    }
    (args.output / "study-scope.json").write_text(json.dumps(note, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(run())

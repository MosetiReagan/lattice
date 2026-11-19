"""Repository convenience command for the Phase C CPU protocol."""

import argparse
import asyncio
from pathlib import Path

from lattice.config import load_settings
from lattice.evaluation.benchmark import run_benchmark

parser = argparse.ArgumentParser()
parser.add_argument("--config", default="configs/local.json")
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--trials", type=int)
parser.add_argument("--warmups", type=int)
parser.add_argument("--workloads", nargs="+")
parser.add_argument("--quality", action="store_true")
args = parser.parse_args()
settings = load_settings(args.config)
asyncio.run(
    run_benchmark(
        settings,
        settings.models[0].id,
        Path("benchmarks/workloads/cpu-v1.json"),
        args.output,
        args.trials,
        args.warmups,
        args.workloads,
        Path("benchmarks/datasets/quality-smoke.json") if args.quality else None,
    )
)

"""Reproduce two sequential, order-varied precision benchmark blocks."""

import argparse
import datetime
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = [
    "qwen2.5-0.5b-instruct-f16",
    "qwen2.5-0.5b-instruct-q8_0",
    "qwen2.5-0.5b-instruct-q4_k_m",
]
ORDERS = [
    [
        "qwen2.5-0.5b-instruct-q8_0",
        "qwen2.5-0.5b-instruct-f16",
        "qwen2.5-0.5b-instruct-q4_k_m",
    ],
    [
        "qwen2.5-0.5b-instruct-q4_k_m",
        "qwen2.5-0.5b-instruct-q8_0",
        "qwen2.5-0.5b-instruct-f16",
    ],
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Fresh directory; no previous results are overwritten",
    )
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument(
        "--quality", action=argparse.BooleanOptionalAction, default=True
    )
    args = parser.parse_args()
    if not 1 <= args.trials <= 1000 or not 0 <= args.warmups <= 20:
        raise ValueError("Trials must be 1..1000 and warmups 0..20")
    args.output_root = (
        args.output_root if args.output_root.is_absolute() else ROOT / args.output_root
    )
    args.output_root.mkdir(parents=True, exist_ok=False)
    workload = ROOT / "benchmarks/workloads/cpu-v2-followup.json"
    digest = hashlib.sha256(workload.read_bytes()).hexdigest()
    record = {
        "started_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "workload_file": str(workload.relative_to(ROOT)),
        "workload_sha256": digest,
        "trial_count": args.trials,
        "warmup_count": args.warmups,
        "quality_smoke": args.quality,
        "native_slots": 1,
        "order_by_block": ORDERS,
        "blocks": {},
        "note": "Sequential single-slot runs; concurrent/mixed profiles test queueing, not native batching. No benchmark blocks overlap.",
    }
    path = args.output_root / "orchestration.json"
    path.write_text(json.dumps(record, indent=2) + "\n")
    for index, order in enumerate(ORDERS, start=1):
        block = args.output_root / f"block-{index}"
        block.mkdir()
        status = {}
        record["blocks"][str(index)] = {
            "path": str(block.relative_to(ROOT)),
            "status": status,
        }
        path.write_text(json.dumps(record, indent=2) + "\n")
        for model in order:
            output = block / model
            command = [
                str(ROOT / ".venv/bin/lattice"),
                "benchmark",
                "--model",
                model,
                "--output",
                str(output),
                "--workload-file",
                str(workload),
                "--trials",
                str(args.trials),
                "--warmups",
                str(args.warmups),
            ]
            if args.quality:
                command.append("--quality")
            with (args.output_root / "runner.log").open("a") as log:
                log.write(
                    f"\nSTART block={index} model={model} utc={datetime.datetime.now(datetime.UTC).isoformat()}\n"
                )
                log.flush()
                exit_code = subprocess.run(
                    command, check=False, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT
                ).returncode
            status[model] = {
                "exit_code": exit_code,
                "summary_exists": (output / "summary.json").exists(),
                "completed_utc": datetime.datetime.now(datetime.UTC).isoformat(),
            }
            path.write_text(json.dumps(record, indent=2) + "\n")
            if exit_code:
                record["status"] = "failed"
                path.write_text(json.dumps(record, indent=2) + "\n")
                raise SystemExit(f"Benchmark failed for {model}; raw output preserved")
    record["status"] = "completed"
    record["finished_utc"] = datetime.datetime.now(datetime.UTC).isoformat()
    path.write_text(json.dumps(record, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output_root),
                "blocks": 2,
                "models_per_block": len(MODELS),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

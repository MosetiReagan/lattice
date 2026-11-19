"""Measure authored prompt lengths with the pinned Qwen chat tokenizer.

Row tiers are not token counts. This is tokenizer compatibility data, not model
quality, latency or long-context correctness evidence.
"""

import argparse
import asyncio
import json
from collections import defaultdict
from pathlib import Path

import httpx

from lattice.backends import create_backend
from lattice.config import file_hash, load_settings, select_model
from lattice.data.schema import DataRecord
from lattice.optimizations.speculative.compatibility import tokenizer_fingerprint

ROOT = Path(__file__).resolve().parents[2]


def quantile(values, p):
    values = sorted(values)
    position = (len(values) - 1) * p
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-for-quality", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "benchmarks/results/dataset-token-lengths-v1",
    )
    args = parser.parse_args()
    if args.wait_for_quality:
        while not (
            ROOT / "benchmarks/results/dataset-quality-v1/completed.json"
        ).exists():
            await asyncio.sleep(5)
    args.output.mkdir(parents=True, exist_ok=False)
    settings = load_settings()
    settings.native_slots = 1
    settings.context_tokens = 2048
    model = select_model(settings, "qwen2.5-0.5b-instruct-f16")
    if file_hash(Path(model.path)) != model.sha256:
        raise RuntimeError("Tokenizer model hash changed")
    manifest_path = ROOT / "benchmarks/datasets/generated/intake-v1/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    grouped = defaultdict(list)
    backend = create_backend(settings, model)
    count = 0
    try:
        await backend.start()
        async with httpx.AsyncClient(
            base_url=backend.base_url,
            headers=backend.headers,
            timeout=60.0,
            trust_env=False,
        ) as client:
            with (args.output / "lengths.jsonl").open("w") as output:
                for file in manifest["files"]:
                    path = ROOT / file["path"]
                    if file_hash(path) != file["sha256"]:
                        raise RuntimeError("Generated dataset checksum mismatch")
                    for line in path.read_text().splitlines():
                        record = DataRecord.model_validate_json(line)
                        formatted = await backend._post(
                            client,
                            "/apply-template",
                            {"messages": [{"role": "user", "content": record.prompt}]},
                        )
                        encoded = await backend._post(
                            client,
                            "/tokenize",
                            {
                                "content": formatted["prompt"],
                                "add_special": True,
                                "parse_special": True,
                            },
                        )
                        tokens = len(encoded["tokens"])
                        group = (
                            record.dataset
                            + ":"
                            + str(record.metadata.get("nominal_rows_tier", "all"))
                        )
                        grouped[group].append(tokens)
                        output.write(
                            json.dumps(
                                {
                                    "id": record.id,
                                    "dataset": record.dataset,
                                    "partition": record.partition,
                                    "template": record.metadata["template"],
                                    "nominal_rows_tier": record.metadata.get(
                                        "nominal_rows_tier"
                                    ),
                                    "prompt_sha256": record.prompt_sha256(),
                                    "chat_prompt_tokens": tokens,
                                    "input_utf8_bytes": len(record.prompt.encode()),
                                }
                            )
                            + "\n"
                        )
                        count += 1
    finally:
        backend.stop()
    report = {
        "records": count,
        "model_sha256": model.sha256,
        "tokenizer_fingerprint": tokenizer_fingerprint(Path(model.path)),
        "backend_commit": settings.backend_commit,
        "backend_sha256": settings.backend_sha256,
        "dataset_manifest_sha256": file_hash(manifest_path),
        "runner_sha256": file_hash(Path(__file__)),
        "lengths_sha256": file_hash(args.output / "lengths.jsonl"),
        "protocol": "Pinned Qwen user chat template, add_special=true, parse_special=true; lengths only, no truncation or generation",
        "groups": {},
    }
    for group, values in sorted(grouped.items()):
        report["groups"][group] = {
            "records": len(values),
            "minimum": min(values),
            "maximum": max(values),
            "p50": quantile(values, 0.5),
            "p90": quantile(values, 0.9),
            "p95": quantile(values, 0.95),
            "p99": quantile(values, 0.99),
            "exceeds_2k_with_32_output_tokens": sum(v + 32 > 2048 for v in values),
        }
    (args.output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

"""Export measured evaluation observations, never training/qualification labels."""

import argparse
import csv
import json
from pathlib import Path

from lattice.config import file_hash

ROOT = Path(__file__).resolve().parents[1]
FIELDS = [
    "model",
    "model_sha256",
    "precision",
    "dataset",
    "id",
    "stratum",
    "source_license",
    "status",
    "context_tokens",
    "prompt_tokens",
    "max_output_tokens",
    "completion_tokens",
    "finish_reason",
    "strategy",
    "score_status",
    "answer_correct",
    "strict_correct",
    "span_token_f1",
    "extraction",
    "operational_seconds",
    "prompt_sha256",
    "reference_sha256",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-larger-model", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "benchmarks/results/dataset-observations-v1",
    )
    args = parser.parse_args()
    sources = [ROOT / "benchmarks/results/dataset-quality-v1"]
    if args.include_larger_model:
        sources.append(ROOT / "benchmarks/results/dataset-quality-1.5b-v1")
    rows = []
    provenance = []
    seen = set()
    for folder in sources:
        completed = json.loads((folder / "completed.json").read_text())
        manifest = json.loads((folder / "manifest.json").read_text())
        for model in completed["models"]:
            artifact = manifest["models"][model]
            path = folder / (model + ".jsonl")
            provenance.append(
                {"path": str(path.relative_to(ROOT)), "sha256": file_hash(path)}
            )
            for line in path.read_text().splitlines():
                item = json.loads(line)
                key = model, item["id"]
                if key in seen:
                    raise ValueError("Duplicate observation")
                seen.add(key)
                score = item.get("score") or {}
                rows.append(
                    dict(
                        zip(
                            FIELDS,
                            [
                                model,
                                artifact["sha256"],
                                artifact["precision"],
                                item["dataset"],
                                item["id"],
                                item["stratum"],
                                item["license"],
                                item["status"],
                                manifest["context_tokens"],
                                item.get("prompt_tokens"),
                                item["max_tokens"],
                                item.get("completion_tokens"),
                                item.get("finish_reason"),
                                item.get("selected_strategy"),
                                score.get("status"),
                                score.get("answer_correct"),
                                score.get("strict_correct"),
                                score.get("metrics", {}).get("token_f1"),
                                score.get("details", {}).get("extraction"),
                                item.get("operational_seconds"),
                                item["prompt_sha256"],
                                item["reference_sha256"],
                            ],
                            strict=True,
                        )
                    )
                )
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.output / "observations.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (args.output / "observations.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows)
    )
    report = {
        "version": "intake-observations-v1",
        "observations": len(rows),
        "unique_tasks": len({r["id"] for r in rows}),
        "models": sorted({r["model"] for r in rows}),
        "source_files": provenance,
        "csv_sha256": file_hash(args.output / "observations.csv"),
        "jsonl_sha256": file_hash(args.output / "observations.jsonl"),
        "exporter_sha256": file_hash(Path(__file__)),
        "policy_use": "Frozen evaluation only; do not train a controller or tune thresholds on these outcomes",
        "timing": "Operational seconds include tokenization and wrapper overhead on a shared VM; not isolated latency/throughput labels",
        "quality": "Lattice generated-answer scoring, not official leaderboard scores; null score fields never count as failures or passes",
        "license": "Source terms retained per observation; no blanket relicensing of external data",
        "counting": "Multiple model outputs for one task are observations, not new task records",
    }
    (args.output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

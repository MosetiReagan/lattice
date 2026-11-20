"""Re-score actual outputs and verify model/case coverage against frozen inputs."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from lattice.config import file_hash
from lattice.data.schema import DataRecord
from lattice.data.scoring import score_record

ROOT = Path(__file__).resolve().parents[1]


def validate(folder):
    completed = json.loads((folder / "completed.json").read_text())
    manifest = json.loads((folder / "manifest.json").read_text())
    frozen_path = ROOT / "benchmarks/datasets/eval-subsets-v1.json"
    if file_hash(frozen_path) != manifest["frozen_subset_sha256"]:
        raise ValueError("Frozen evaluation selection changed")
    if file_hash(ROOT / "src/lattice/data/scoring.py") != manifest["scorer_sha256"]:
        raise ValueError("Scorer changed; explicit historical scorer required")
    frozen = json.loads(frozen_path.read_text())
    records = {}
    for dataset in frozen["datasets"]:
        path = ROOT / dataset["source_file"]
        if file_hash(path) != dataset["source_sha256"]:
            raise ValueError("Frozen source changed")
        wanted = {r["id"] for r in dataset["selected"]}
        for line in path.read_text().splitlines():
            record = DataRecord.model_validate_json(line)
            if record.id in wanted:
                records[record.id] = record
    result = {"frozen_cases": len(records), "models": {}}
    for model in completed["models"]:
        path = folder / (model + ".jsonl")
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        if len(rows) != len(records) or {r["id"] for r in rows} != records.keys():
            raise ValueError("Incomplete or duplicate outcome coverage")
        passed = 0
        skipped = 0
        errors = []
        for row in rows:
            record = records[row["id"]]
            if (
                row["prompt_sha256"] != record.prompt_sha256()
                or row["reference_sha256"] != record.reference_sha256()
            ):
                raise ValueError("Outcome input/reference differs from frozen case")
            if row["max_tokens"] != manifest["output_caps"][record.dataset]:
                raise ValueError("Output cap changed")
            if row["status"] == "completed":
                if row["selected_strategy"] != "standard":
                    raise ValueError("Baseline silently changed strategy")
                if not 0 <= row["completion_tokens"] <= row["max_tokens"]:
                    raise ValueError("Output cap violated")
                if (
                    row["prompt_tokens"] + row["max_tokens"]
                    > manifest["context_tokens"]
                ):
                    raise ValueError("Overlength baseline was served")
                if asdict(score_record(record, row["text"])) != row["score"]:
                    raise ValueError("Stored score cannot be reproduced")
                passed += 1
            elif row["status"] == "skipped_context_limit":
                if (
                    row["prompt_tokens"] + row["max_tokens"]
                    <= manifest["context_tokens"]
                    and len(record.prompt.encode()) <= 32768
                ):
                    raise ValueError(
                        "Unsupported skip without a context/byte-limit reason"
                    )
                if row["score"] is not None:
                    raise ValueError("Skipped case was scored")
                skipped += 1
            else:
                errors.append({"id": row["id"], "status": row["status"]})
        result["models"][model] = {
            "observations": len(rows),
            "reproduced_scores": passed,
            "verified_context_skips": skipped,
            "other_errors": errors,
            "outcomes_sha256": file_hash(path),
        }
    result["validator_sha256"] = file_hash(Path(__file__))
    result["policy_qualification"] = False
    (folder / "observation-validation.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results", type=Path, default=ROOT / "benchmarks/results/dataset-quality-v1"
    )
    args = parser.parse_args()
    print(json.dumps(validate(args.results), indent=2))


if __name__ == "__main__":
    main()

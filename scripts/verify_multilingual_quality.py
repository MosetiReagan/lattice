"""Replay multilingual scores and check coverage against the frozen sample."""

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from lattice.config import file_hash
from lattice.data.schema import DataRecord

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments/datasets"))
from multilingual_quality import SUBSET, score_span


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    folder = parser.parse_args().results
    manifest = json.loads((folder / "manifest.json").read_text())
    completed = json.loads((folder / "completed.json").read_text())
    if manifest["frozen_subset_sha256"] != file_hash(SUBSET):
        raise ValueError("Frozen subset mismatch")
    if manifest["scorer_sha256"] != file_hash(
        ROOT / "experiments/datasets/multilingual_quality.py"
    ):
        raise ValueError("Scorer source mismatch")
    records = {}
    for source in json.loads(SUBSET.read_text())["datasets"]:
        path = ROOT / source["source_file"]
        if file_hash(path) != source["source_sha256"]:
            raise ValueError("Source mismatch")
        ids = {row["id"] for row in source["selected"]}
        with path.open() as stream:
            for line in stream:
                record = DataRecord.model_validate_json(line)
                if record.id in ids:
                    records[record.id] = record
    if len(records) != completed["records_per_model"]:
        raise ValueError("Incomplete subset")
    report = {}
    tokenizations = {}
    for model in completed["models"]:
        path = folder / f"{model}.jsonl"
        seen = set()
        counts = Counter()
        for line in path.read_text().splitlines():
            row = json.loads(line)
            record = records[row["id"]]
            if (
                record.id in seen
                or row["prompt_sha256"] != record.prompt_sha256()
                or row["reference_sha256"] != record.reference_sha256()
            ):
                raise ValueError("Duplicate or changed case")
            seen.add(record.id)
            if row["max_tokens"] != manifest["output_caps"][record.dataset]:
                raise ValueError("Output budget changed")
            token_count = row.get("prompt_tokens")
            if tokenizations.setdefault(record.id, token_count) != token_count:
                raise ValueError("Model prompt token counts differ")
            counts[row["status"]] += 1
            if row["status"] == "completed":
                if (
                    row["score"] != asdict(score_span(record, row["text"]))
                    or row["selected_strategy"] != "standard"
                    or not 0 <= row["completion_tokens"] <= row["max_tokens"]
                    or row["prompt_tokens"] + row["max_tokens"]
                    > manifest["context_tokens"]
                ):
                    raise ValueError("Score or runtime contract mismatch")
                counts["unicode_exact_match"] += row["score"]["answer_correct"]
                counts["strict_exact_match"] += row["score"]["strict_correct"]
                counts["output_cap_finishes"] += row["finish_reason"] == "length"
        if seen != records.keys():
            raise ValueError("Incomplete observations")
        report[model] = dict(counts, outcomes_sha256=file_hash(path))
    (folder / "verified.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

"""Re-score 8k retrieval and verify tokenization against the frozen 2k run."""

import json
from dataclasses import asdict
from pathlib import Path

from lattice.config import file_hash
from lattice.data.schema import DataRecord
from lattice.data.scoring import score_record

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / "benchmarks/results/dataset-long-context-v1"
    manifest = json.loads((folder / "manifest.json").read_text())
    frozen_path = ROOT / "benchmarks/datasets/eval-subsets-curated-v1.json"
    assert file_hash(frozen_path) == manifest["frozen_subset_sha256"]
    frozen = json.loads(frozen_path.read_text())
    selection = next(
        d for d in frozen["datasets"] if d["dataset"] == "lattice_retrieval"
    )
    path = ROOT / selection["source_file"]
    assert file_hash(path) == selection["source_sha256"]
    records = {
        r.id: r
        for line in path.read_text().splitlines()
        if (r := DataRecord.model_validate_json(line))
    }
    expected = {r["id"] for r in selection["selected"]}
    baseline_path = (
        ROOT / "benchmarks/results/dataset-quality-v1/qwen2.5-0.5b-instruct-f16.jsonl"
    )
    baseline = {
        r["id"]: r
        for line in baseline_path.read_text().splitlines()
        if (r := json.loads(line))["id"] in expected
    }
    rows = [
        json.loads(line)
        for line in (folder / "outcomes.jsonl").read_text().splitlines()
    ]
    assert len(rows) == len(expected) == 60 and {r["id"] for r in rows} == expected
    scored = 0
    errors = []
    for row in rows:
        record = records[row["id"]]
        assert (
            row["prompt_sha256"]
            == record.prompt_sha256()
            == baseline[row["id"]]["prompt_sha256"]
        )
        assert (
            row["reference_sha256"]
            == record.reference_sha256()
            == baseline[row["id"]]["reference_sha256"]
        )
        if row["status"] != "completed":
            errors.append({"id": row["id"], "status": row["status"]})
            continue
        assert row["prompt_tokens"] == baseline[row["id"]]["prompt_tokens"]
        assert row["prompt_tokens"] + 32 <= 8192
        assert 0 <= row["completion_tokens"] <= 32
        assert asdict(score_record(record, row["text"])) == row["score"]
        scored += 1
    report = {
        "selected": len(rows),
        "scores_reproduced": scored,
        "other_errors": errors,
        "all_completed_tokenizations_match_2k_baseline": True,
        "no_truncation_or_output_limit_violations": True,
        "validator_sha256": file_hash(Path(__file__)),
        "outcomes_sha256": file_hash(folder / "outcomes.jsonl"),
        "baseline_outcomes_sha256": file_hash(baseline_path),
        "scope": "Frozen synthetic retrieval only; no universal equivalence or broad long-context quality claim",
    }
    (folder / "observation-validation.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

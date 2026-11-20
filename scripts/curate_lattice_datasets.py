"""Materialize a conservative semantic-quality view without rewriting originals.

The original generator's arithmetic remains reproducible. Inventory questions
that physically remove more objects than exist are quarantined rather than
silently reworded or used as legitimate negative-stock word problems.
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from lattice.config import file_hash
from lattice.data.schema import DataRecord

ROOT = Path(__file__).resolve().parents[1]


def issues(record: DataRecord) -> list[str]:
    result = []
    if (
        record.dataset == "lattice_arithmetic"
        and record.metadata.get("template") == "inventory_word_problem"
    ):
        match = re.search(
            r"has (\d+) boxes, with (\d+) bolts per box\. Workers remove (\d+) bolts",
            record.prompt,
        )
        if not match:
            raise ValueError(
                "Inventory template changed; semantic audit must be reviewed"
            )
        boxes, per_box, removed = map(int, match.groups())
        if removed > boxes * per_box:
            result.append("physical_inventory_removal_exceeds_available_stock")
    if record.dataset == "lattice_retrieval":
        # These generated records require one distinct entry per base key.
        keys = re.findall(
            r"^(?:version 1: )?(k[0-9a-f]+) = ", record.prompt, re.MULTILINE
        )
        if len(keys) != len(set(keys)):
            result.append("duplicate_base_retrieval_key")
    return result


def curate(manifest_path: Path, output: Path) -> dict:
    source = json.loads(manifest_path.read_text())
    output.mkdir(parents=True, exist_ok=False)
    files = []
    rejected = []
    counts = Counter()
    for entry in source["files"]:
        path = ROOT / entry["path"]
        if file_hash(path) != entry["sha256"]:
            raise ValueError("Original generated data changed")
        target = output / entry["dataset"] / (entry["partition"] + ".jsonl")
        target.parent.mkdir(exist_ok=True)
        count = 0
        with path.open() as stream, target.open("w") as destination:
            for line in stream:
                record = DataRecord.model_validate_json(line)
                reasons = issues(record)
                if reasons:
                    rejected.append(
                        {
                            "id": record.id,
                            "dataset": record.dataset,
                            "partition": record.partition,
                            "reasons": reasons,
                            "prompt_sha256": record.prompt_sha256(),
                            "reference_sha256": record.reference_sha256(),
                            "original_file": entry["path"],
                        }
                    )
                    continue
                destination.write(line)
                counts[record.dataset] += 1
                count += 1
        files.append(
            {
                "dataset": entry["dataset"],
                "partition": entry["partition"],
                "rows": count,
                "path": str(target.relative_to(ROOT)),
                "sha256": file_hash(target),
                "bytes": target.stat().st_size,
            }
        )
    manifest = {
        "version": "intake-v1-curated",
        "parent_version": source["version"],
        "source_manifest_sha256": file_hash(manifest_path),
        "curator_sha256": file_hash(Path(__file__)),
        "source_records": source["records"],
        "records": sum(counts.values()),
        "quarantined_records": len(rejected),
        "dataset_counts": dict(counts),
        "files": files,
        "quarantine": rejected,
        "policy": "No repairs or relabeling; original files and historical frozen evaluation selections preserved",
        "known_rubric_limitations": [
            "Instruction exact-text checks require canonical whitespace; they measure declared canonical-rubric compliance and can reject other semantically valid instruction responses."
        ],
        "audit_scope": "Deterministic authored-template invariants, not a complete semantic quality or near-duplicate audit",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "benchmarks/datasets/generated/intake-v1-curated",
    )
    args = parser.parse_args()
    manifest = curate(
        ROOT / "benchmarks/datasets/generated/intake-v1/manifest.json", args.output
    )
    report = ROOT / "benchmarks/datasets/manifests/generated-curated-intake-v1.json"
    report.write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: manifest[k]
                for k in ["source_records", "records", "quarantined_records"]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

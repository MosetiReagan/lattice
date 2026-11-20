"""Freeze deterministic, stratified evaluation IDs before any model outcomes."""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from lattice.config import file_hash
from lattice.data.schema import DataRecord

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED = {
    "number_v1",
    "choice_v1",
    "boolean_v1",
    "span_v1",
    "json_v1",
    "constraints_v1",
    "text_v1",
}


def stratum(record):
    if record.metadata.get("synthetic"):
        return (
            record.metadata["template"]
            + ":"
            + str(record.metadata.get("nominal_rows_tier", ""))
        )
    if record.reference.kind == "choice":
        return record.reference.value
    if record.reference.kind == "boolean":
        return str(record.reference.value)
    if record.reference.kind == "span":
        return str(bool(record.reference.alternatives))
    return "all"


def select(records, count, seed):
    groups = defaultdict(list)
    for record in records:
        groups[stratum(record)].append(record)
    for rows in groups.values():
        rows.sort(key=lambda r: hashlib.sha256(f"{seed}:{r.id}".encode()).hexdigest())
    selected = []
    keys = sorted(groups)
    while len(selected) < count and keys:
        for key in keys[:]:
            if groups[key]:
                selected.append(groups[key].pop(0))
                if len(selected) == count:
                    break
            else:
                keys.remove(key)
    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--seed", type=int, default=84721)
    parser.add_argument(
        "--catalog", type=Path, default=ROOT / "benchmarks/datasets/catalog-v1.json"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "benchmarks/datasets/eval-subsets-v1.json"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify checked-in selections without overwriting provenance",
    )
    args = parser.parse_args()
    if args.output.exists() and not args.verify:
        raise SystemExit(
            "Frozen subsets already exist; choose an explicitly new output"
        )
    catalog_path = args.catalog
    catalog = json.loads(catalog_path.read_text())
    result = {
        "version": "intake-eval-v1",
        "seed": args.seed,
        "selection": "Equal round-robin quota by task template/row tier or reference class, hash ranked within stratum; may differ from source class prevalence",
        "catalog_sha256": file_hash(catalog_path),
        "policy_use": "Frozen evaluation only, not controller training or threshold tuning",
        "datasets": [],
    }
    for entry in catalog["files"]:
        if entry["partition"] != "evaluation":
            continue
        path = ROOT / entry["path"]
        if file_hash(path) != entry["sha256"]:
            raise ValueError("Checksum mismatch")
        records = [
            DataRecord.model_validate_json(line)
            for line in path.read_text().splitlines()
        ]
        if not records or records[0].scorer not in SUPPORTED:
            continue
        selected = select(records, args.count, args.seed)
        result["datasets"].append(
            {
                "dataset": entry["dataset"],
                "source_file": entry["path"],
                "source_sha256": entry["sha256"],
                "available_evaluation_records": len(records),
                "selected": [
                    {
                        "id": r.id,
                        "prompt_sha256": r.prompt_sha256(),
                        "reference_sha256": r.reference_sha256(),
                        "stratum": stratum(r),
                    }
                    for r in selected
                ],
            }
        )
    if args.verify:
        existing = json.loads(args.output.read_text())
        # Manifest timestamps differ after a rebuild; data hashes and selections must not.
        for key, value in result.items():
            if key != "catalog_sha256" and value != existing.get(key):
                raise ValueError("Frozen evaluation selection changed: " + key)
    else:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        "Frozen",
        sum(len(d["selected"]) for d in result["datasets"]),
        "records in",
        len(result["datasets"]),
        "configurations",
    )


if __name__ == "__main__":
    main()

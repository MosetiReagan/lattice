"""Audit new multilingual exports against the preserved curated intake."""

import json
from collections import Counter
from pathlib import Path

from lattice.config import file_hash
from lattice.data.schema import DataRecord

ROOT = Path(__file__).resolve().parents[1]


def main():
    catalog_path = ROOT / "benchmarks/datasets/catalog-curated-v1.json"
    catalog = json.loads(catalog_path.read_text())
    existing = {}
    for entry in catalog["files"]:
        path = ROOT / entry["path"]
        if file_hash(path) != entry["sha256"]:
            raise ValueError("Historical catalog checksum drift")
        with path.open() as stream:
            for line in stream:
                record = DataRecord.model_validate_json(line)
                existing[record.content_sha256()] = record.partition
    seen = set()
    overlaps = Counter()
    cross_new = 0
    new_count = 0
    manifests = []
    for name in ["tydiqa", "xquad"]:
        path = ROOT / f"benchmarks/datasets/manifests/{name}-v1.json"
        manifest = json.loads(path.read_text())
        source = ROOT / manifest["path"]
        if file_hash(source) != manifest["sha256"]:
            raise ValueError("New export checksum drift")
        count = 0
        for line in source.read_text().splitlines():
            record = DataRecord.model_validate_json(line)
            assert record.partition == "evaluation"
            digest = record.content_sha256()
            if digest in existing:
                overlaps[existing[digest]] += 1
            if digest in seen:
                cross_new += 1
            seen.add(digest)
            count += 1
        if count != manifest["records"]:
            raise ValueError("Manifest count mismatch")
        new_count += count
        manifests.append(
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": file_hash(path),
                "records": count,
            }
        )
    report = {
        "version": "multilingual-additions-v1",
        "historical_curated_records": catalog["prepared_records"],
        "additional_exported_records": new_count,
        "new_unique_normalized_prompts": len(seen),
        "cross_addition_duplicate_prompts": cross_new,
        "overlap_with_historical_by_partition": dict(overlaps),
        "new_prompts_absent_from_historical": len(seen - existing.keys()),
        "union_unique_normalized_prompts": len(existing.keys() | seen),
        "manifests": manifests,
        "historical_catalog_sha256": file_hash(catalog_path),
        "audit_script_sha256": file_hash(Path(__file__)),
        "policy": "New additions are evaluation-only. XQuAD derives from SQuAD; prohibit policy training on related historical source data when evaluating these additions. Exact matching does not detect all shared contexts or translated semantic overlaps.",
        "not_claimed": [
            "New exports are not all independent tasks.",
            "No official multilingual scorer validation or model quality results.",
            "No public-data contamination guarantee.",
        ],
    }
    (ROOT / "benchmarks/datasets/manifests/multilingual-additions-v1.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

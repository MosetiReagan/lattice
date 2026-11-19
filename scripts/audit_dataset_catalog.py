"""Verify every prepared record and freeze a compact, redistributable inventory."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from lattice.config import file_hash
from lattice.data.schema import DataRecord
from lattice.data.scoring import score_record

ROOT = Path(__file__).resolve().parents[1]


def audit(manifests: list[Path]) -> dict:
    prompts = set()
    identifiers = set()
    groups = {}
    inventories = defaultdict(
        lambda: {
            "partitions": Counter(),
            "scorers": Counter(),
            "labels": Counter(),
            "templates": Counter(),
            "rows_tiers": Counter(),
            "licenses": set(),
        }
    )
    files = []
    gold_checks = 0
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text())
        for entry in manifest["files"]:
            path = ROOT / entry["path"]
            if file_hash(path) != entry["sha256"]:
                raise ValueError("Prepared checksum mismatch: " + str(path))
            count = 0
            with path.open() as stream:
                for line in stream:
                    record = DataRecord.model_validate_json(line)
                    digest = record.content_sha256()
                    if digest in prompts or record.id in identifiers:
                        raise ValueError(
                            "Duplicate active prompt or identifier: " + record.id
                        )
                    prompts.add(digest)
                    identifiers.add(record.id)
                    if record.partition != "corpus":
                        key = record.family, record.group_id
                        if key in groups and groups[key] != record.partition:
                            raise ValueError("Source group crosses policy partitions")
                        groups[key] = record.partition
                    if (
                        record.partition != entry["partition"]
                        or record.dataset != entry["dataset"]
                    ):
                        raise ValueError("Record does not match its manifest")
                    item = inventories[record.dataset]
                    item["partitions"][record.partition] += 1
                    item["scorers"][record.scorer] += 1
                    item["licenses"].add(record.license)
                    item["family"] = record.family
                    if record.reference.kind in ("choice", "boolean"):
                        item["labels"][json.dumps(record.reference.value)] += 1
                    if "answerable" in record.metadata:
                        item["labels"][
                            "answerable:" + str(record.metadata["answerable"])
                        ] += 1
                    if "template" in record.metadata:
                        item["templates"][
                            record.partition + ":" + record.metadata["template"]
                        ] += 1
                    if "nominal_rows_tier" in record.metadata:
                        item["rows_tiers"][
                            record.partition
                            + ":"
                            + str(record.metadata["nominal_rows_tier"])
                        ] += 1
                    if record.metadata.get("synthetic"):
                        score = score_record(
                            record, record.metadata["canonical_response"]
                        )
                        if (
                            score.status != "scored"
                            or not score.answer_correct
                            or not score.strict_correct
                        ):
                            raise ValueError(
                                "Canonical synthetic reference failed: " + record.id
                            )
                        gold_checks += 1
                    count += 1
            if count != entry["rows"]:
                raise ValueError("Row count mismatch")
            files.append(entry)
    for item in inventories.values():
        item["licenses"] = sorted(item["licenses"])
        item["records"] = sum(item["partitions"].values())
        item["unit"] = "article document" if item["family"] == "wikitext" else "task"
    return {
        "schema_version": 1,
        "version": "intake-v1",
        "external_source_families": 9,
        "external_configurations": 10,
        "authored_suites": 4,
        "prepared_records": len(identifiers),
        "task_records": sum(
            v["records"] for v in inventories.values() if v["unit"] == "task"
        ),
        "article_documents": sum(
            v["records"] for v in inventories.values() if v["unit"] != "task"
        ),
        "canonical_synthetic_references_checked": gold_checks,
        "exact_prompt_duplicates": 0,
        "policy_group_leakage": 0,
        "datasets": dict(sorted(inventories.items())),
        "files": files,
        "input_manifests": [
            {"path": str(p.relative_to(ROOT)), "sha256": file_hash(p)}
            for p in manifests
        ],
        "claims": [
            "Checks cover exported active partitions, not foundation-model pretraining contamination.",
            "Code/official IFEval collected but unscored; corpus documents are not QA examples.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "benchmarks/datasets/catalog-v1.json"
    )
    args = parser.parse_args()
    report = audit(
        [
            ROOT / "benchmarks/datasets/external/prepared/intake-v1/manifest.json",
            ROOT / "benchmarks/datasets/generated/intake-v1/manifest.json",
        ]
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: report[k]
                for k in [
                    "prepared_records",
                    "task_records",
                    "article_documents",
                    "canonical_synthetic_references_checked",
                ]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

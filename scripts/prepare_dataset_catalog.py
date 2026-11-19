"""Normalize locked sources, audit gold/overlap, preserve source and policy splits.

All external prepared examples stay under external/. No remote code executes.
Quarantined records are counted with reasons; no source labels are repaired by a model.
"""

import argparse
import ast
import datetime
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

from lattice.config import file_hash
from lattice.data.normalize import normalize_row, source_rows, wiki_documents
from lattice.data.schema import DataRecord

ROOT = Path(__file__).resolve().parents[1]
RANK = {"corpus": 0, "development": 1, "validation": 2, "evaluation": 3}


def partition(record: DataRecord, spec: dict) -> str:
    split = record.source_split
    if record.partition == "corpus":
        return "corpus"
    bucket = (
        int(
            hashlib.sha256(
                ("lattice-policy-split-v1:" + record.group_id).encode()
            ).hexdigest()[:8],
            16,
        )
        % 100
    )
    splits = {f["split"] for f in spec["files"]}
    if split == "test":
        return "evaluation"
    if split == "validation":
        return "validation" if "test" in splits else "evaluation"
    if split == "prompt":
        return "development"
    if splits == {"train"}:
        return (
            "evaluation"
            if bucket < 20
            else ("validation" if bucket < 40 else "development")
        )
    return "validation" if bucket < 20 else "development"


def validate_reference(record: DataRecord) -> None:
    if record.reference.kind == "program":
        value = record.reference.value
        code = value.get("prompt_prefix", "") + value["canonical_solution"]
        ast.parse(code)
        if "test" in value:
            ast.parse(value["test"])
        else:
            ast.parse(value.get("test_setup_code", ""))
            for test in value["test_list"] + value.get("challenge_test_list", []):
                ast.parse(test)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="intake-v1")
    args = parser.parse_args()
    source_lock = ROOT / "benchmarks/datasets/sources.lock.json"
    lock = json.loads(source_lock.read_text())
    download_path = ROOT / "benchmarks/datasets/external/download-manifest.json"
    downloads = json.loads(download_path.read_text())
    if file_hash(source_lock) != downloads["source_lock_sha256"]:
        raise SystemExit("Source lock changed after download")
    folder = ROOT / "benchmarks/datasets/external/prepared" / args.version
    folder.mkdir(parents=True, exist_ok=False)
    db = sqlite3.connect(folder / "audit.sqlite3")
    db.execute(
        "CREATE TABLE records(id TEXT PRIMARY KEY,dataset TEXT,family TEXT,split TEXT,partition TEXT,rank INT,group_id TEXT,input_hash TEXT,gold_hash TEXT,row_json TEXT,keep INT DEFAULT 1,reason TEXT)"
    )
    raw_counts = Counter()
    valid_counts = Counter()
    invalid = Counter()
    invalid_rows = []
    for spec in lock["collections"]:
        files = [f for f in downloads["files"] if f["collection"] == spec["id"]]
        for file in files:
            path = ROOT / file["path"]
            if file_hash(path) != file["sha256"]:
                raise SystemExit("Raw source checksum mismatch")
            split = file["split"]
            source = (
                list(source_rows(path))
                if spec["id"] == "wikitext2"
                else source_rows(path)
            )
            if spec["id"] == "wikitext2":
                texts = [row["text"] for row in source]
                raw_counts[(spec["id"], split)] = len(texts)
                corpus = folder / spec["id"] / (split + ".txt")
                corpus.parent.mkdir(exist_ok=True)
                corpus.write_text("".join(texts))
                items = wiki_documents(spec, split, texts)
            else:

                def normalize(source=source, spec=spec, split=split):
                    for index, row in enumerate(source):
                        raw_counts[(spec["id"], split)] += 1
                        try:
                            yield normalize_row(spec, split, index, row)
                        except (ValueError, TypeError, KeyError) as exc:
                            invalid[(spec["id"], type(exc).__name__)] += 1
                            invalid_rows.append(
                                {
                                    "dataset": spec["id"],
                                    "split": split,
                                    "row": index,
                                    "reason": str(exc),
                                    "source_row_sha256": hashlib.sha256(
                                        json.dumps(row, sort_keys=True).encode()
                                    ).hexdigest(),
                                }
                            )

                items = normalize()
            for item in items:
                try:
                    validate_reference(item)
                    item.partition = partition(item, spec)
                    db.execute(
                        "INSERT INTO records(id,dataset,family,split,partition,rank,group_id,input_hash,gold_hash,row_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (
                            item.id,
                            item.dataset,
                            item.family,
                            split,
                            item.partition,
                            RANK[item.partition],
                            item.group_id,
                            item.content_sha256(),
                            item.reference_sha256(),
                            item.model_dump_json(),
                        ),
                    )
                    valid_counts[(item.dataset, split)] += 1
                except (
                    ValueError,
                    TypeError,
                    SyntaxError,
                    sqlite3.IntegrityError,
                ) as exc:
                    invalid[(item.dataset, type(exc).__name__)] += 1
                    invalid_rows.append(
                        {
                            "dataset": item.dataset,
                            "split": split,
                            "id": item.id,
                            "reason": str(exc),
                        }
                    )
            db.commit()
    db.execute("CREATE INDEX input_idx ON records(input_hash)")
    db.execute("CREATE INDEX group_idx ON records(family,group_id)")
    # Exact contradictory references are not resolved by guessing or preferential scoring.
    conflicts = db.execute(
        "SELECT input_hash FROM records GROUP BY input_hash HAVING count(DISTINCT gold_hash)>1"
    ).fetchall()
    for (digest,) in conflicts:
        db.execute(
            "UPDATE records SET keep=0,reason='conflicting_reference_for_identical_prompt' WHERE input_hash=?",
            (digest,),
        )
    # Keep highest official policy partition first; all removed duplicates stay in the audit DB.
    duplicate_groups = db.execute(
        "SELECT input_hash FROM records WHERE keep=1 GROUP BY input_hash HAVING count(*)>1"
    ).fetchall()
    for (digest,) in duplicate_groups:
        candidates = db.execute(
            "SELECT id FROM records WHERE input_hash=? AND keep=1 ORDER BY rank DESC,id",
            (digest,),
        ).fetchall()
        for (identifier,) in candidates[1:]:
            db.execute(
                "UPDATE records SET keep=0,reason='exact_prompt_duplicate' WHERE id=?",
                (identifier,),
            )
    # A passage/article/question group cannot appear in both policy development and evaluation.
    mixed = db.execute(
        "SELECT family,group_id,max(rank) FROM records WHERE keep=1 AND partition<>'corpus' GROUP BY family,group_id HAVING count(DISTINCT partition)>1"
    ).fetchall()
    for family, group, rank in mixed:
        db.execute(
            "UPDATE records SET keep=0,reason='group_overlap_with_higher_partition' WHERE family=? AND group_id=? AND keep=1 AND rank<?",
            (family, group, rank),
        )
    db.commit()
    outputs = []
    partitions = Counter()
    handles = {}
    try:
        for dataset, split, row_json in db.execute(
            "SELECT dataset,partition,row_json FROM records WHERE keep=1 ORDER BY dataset,partition,id"
        ):
            key = (dataset, split)
            if key not in handles:
                path = folder / dataset / (split + ".jsonl")
                path.parent.mkdir(exist_ok=True)
                handles[key] = (path, path.open("w"))
            handles[key][1].write(row_json + "\n")
            partitions[key] += 1
    finally:
        for path, stream in handles.values():
            stream.close()
    for (dataset, split), (path, _) in handles.items():
        outputs.append(
            {
                "dataset": dataset,
                "partition": split,
                "rows": partitions[(dataset, split)],
                "path": str(path.relative_to(ROOT)),
                "sha256": file_hash(path),
                "bytes": path.stat().st_size,
            }
        )
    quarantine = [
        {"dataset": dataset, "reason": reason, "rows": count}
        for dataset, reason, count in db.execute(
            "SELECT dataset,reason,count(*) FROM records WHERE keep=0 GROUP BY dataset,reason"
        )
    ]
    invalid_path = folder / "invalid_rows.jsonl"
    invalid_path.write_text("".join(json.dumps(row) + "\n" for row in invalid_rows))
    # Audit assertions are substantive: no exact prompt or source group crosses active partitions.
    assert not db.execute(
        "SELECT input_hash FROM records WHERE keep=1 GROUP BY input_hash HAVING count(*)>1"
    ).fetchall()
    assert not db.execute(
        "SELECT family,group_id FROM records WHERE keep=1 AND partition<>'corpus' GROUP BY family,group_id HAVING count(DISTINCT partition)>1"
    ).fetchall()
    manifest = {
        "schema_version": 1,
        "version": args.version,
        "created_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "source_lock_sha256": file_hash(source_lock),
        "download_manifest_sha256": file_hash(download_path),
        "raw_source_rows": [
            {"dataset": d, "split": s, "rows": n} for (d, s), n in raw_counts.items()
        ],
        "validated_records": sum(valid_counts.values()),
        "prepared_records": sum(partitions.values()),
        "invalid_records": len(invalid_rows),
        "quarantine": quarantine,
        "files": outputs,
        "audit_database": "audit.sqlite3",
        "split_contract": "Official test retained as evaluation. Validation is evaluation where no test is labeled. Train-only IFEval grouped 60/20/20. Other train grouped 80/20 development/validation. Lower-partition group overlaps quarantined.",
        "coding_contract": "References parsed as data; generated/canonical programs were not executed; no pass@k or correctness score claimed",
        "public_data_notice": "Policy partitions are not evidence that foundation model pretraining excluded these public benchmarks",
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    db.close()
    print(
        json.dumps(
            {
                "prepared_records": manifest["prepared_records"],
                "invalid_records": len(invalid_rows),
                "manifest": str(folder / "manifest.json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

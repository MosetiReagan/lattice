"""Reproduce a pinned, data-only multilingual extractive-QA addition."""

import hashlib
import json
import shutil
import urllib.request
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

from lattice.data.schema import DataRecord, Reference

ROOT = Path(__file__).resolve().parents[1]


def prepare():
    lock = json.loads((ROOT / "benchmarks/datasets/tydiqa.lock.json").read_text())
    card = ROOT / "benchmarks/datasets/source_audit/tydiqa-card.txt"
    if hashlib.sha256(card.read_bytes()).hexdigest() != lock["card_sha256"]:
        raise ValueError("Source-card provenance changed")
    folder = ROOT / "benchmarks/datasets/external/tydiqa-v1"
    folder.mkdir(exist_ok=True)
    raw = folder / "validation.parquet"
    if not raw.exists():
        if shutil.disk_usage(ROOT).free < 3 * 1024**3 + lock["bytes"]:
            raise ValueError("Preserve 3 GiB disk reserve")
        with urllib.request.urlopen(lock["url"], timeout=60) as response:
            data = response.read(lock["bytes"] + 1)
        if (
            len(data) != lock["bytes"]
            or hashlib.sha256(data).hexdigest() != lock["sha256"]
        ):
            raise ValueError("Source checksum mismatch")
        raw.write_bytes(data)
    if hashlib.sha256(raw.read_bytes()).hexdigest() != lock["sha256"]:
        raise ValueError("Source checksum mismatch")
    records = []
    seen = set()
    duplicates = []
    invalid_spans = []
    counts = Counter()
    for row in pq.read_table(raw).to_pylist():
        language = row["id"].split("-", 1)[0]
        bad_span = False
        for answer, offset in zip(
            row["answers"]["text"], row["answers"]["answer_start"], strict=True
        ):
            if offset < 0 or row["context"][offset : offset + len(answer)] != answer:
                bad_span = True
        if bad_span:
            invalid_spans.append(row["id"])
            continue
        if not row["answers"]["text"]:
            raise ValueError("Missing gold answer")
        prompt = (
            "Passage:\n"
            + row["context"]
            + "\n\nQuestion: "
            + row["question"]
            + "\n\nReturn only the answer span from the passage."
        )
        digest = hashlib.sha256(prompt.encode()).hexdigest()
        if digest in seen:
            duplicates.append(row["id"])
            continue
        seen.add(digest)
        item = DataRecord(
            id="tydiqa:" + row["id"],
            dataset="tydiqa_goldp",
            family="tydiqa",
            source_split="validation",
            partition="evaluation",
            group_id=hashlib.sha256(
                (language + ":" + row["title"]).encode()
            ).hexdigest(),
            prompt=prompt,
            reference=Reference(
                kind="span", alternatives=list(dict.fromkeys(row["answers"]["text"]))
            ),
            scorer="span_v1",
            license=lock["license"],
            source={
                "repository": lock["repository"],
                "revision": lock["revision"],
                "source_id": row["id"],
                "configuration": "secondary_task",
            },
            metadata={
                "language": language,
                "source_title": row["title"],
                "answerable": True,
                "evaluation_only": True,
                "protocol": "Generated span; English framing around original-language question/context. Existing span normalization is not an official multilingual TyDiQA scorer; no official accuracy claimed.",
            },
        )
        records.append(item)
        counts[language] += 1
    output = folder / "evaluation.jsonl"
    data = "".join(r.model_dump_json() + "\n" for r in records).encode()
    if output.exists() and output.read_bytes() != data:
        raise ValueError("Prepared data changed; version a new intake")
    output.write_bytes(data)
    manifest = {
        "version": "tydiqa-v1",
        "records": len(records),
        "languages": dict(sorted(counts.items())),
        "source_rows": pq.read_metadata(raw).num_rows,
        "duplicate_ids_quarantined": duplicates,
        "invalid_span_ids_quarantined": invalid_spans,
        "path": str(output.relative_to(ROOT)),
        "sha256": hashlib.sha256(data).hexdigest(),
        "source_sha256": lock["sha256"],
        "license": lock["license"],
        "status": "Prepared evaluation-only multilingual spans; model generation not run",
        "limitations": [
            "Wikipedia text retains underlying source obligations; Apache label is dataset-card declaration, not relicensing of underlying articles.",
            "Related article questions are correlated; not independent samples.",
            "No pretraining contamination or semantic near-duplicate guarantee.",
            "Not merged into historical catalog or policy training partitions.",
            "Existing English article/punctuation span normalization is not validated for multilingual official scoring.",
        ],
    }
    report = ROOT / "benchmarks/datasets/manifests/tydiqa-v1.json"
    if report.exists() and json.loads(report.read_text()) != manifest:
        raise ValueError("Manifest changed; preserve previous version")
    report.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    prepare()

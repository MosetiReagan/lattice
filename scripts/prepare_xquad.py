"""Pinned multilingual QA; translations are grouped, never independent families."""

import concurrent.futures
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
    lock = json.loads((ROOT / "benchmarks/datasets/xquad.lock.json").read_text())
    card = ROOT / "benchmarks/datasets/source_audit/xquad-card.txt"
    if hashlib.sha256(card.read_bytes()).hexdigest() != lock["card_sha256"]:
        raise ValueError("Source-card provenance changed")
    folder = ROOT / "benchmarks/datasets/external/xquad-v1"
    folder.mkdir(exist_ok=True)
    if shutil.disk_usage(ROOT).free < 3 * 1024**3:
        raise ValueError("Preserve disk reserve")

    def fetch(entry):
        path = folder / (entry["language"] + ".parquet")
        if not path.exists():
            with urllib.request.urlopen(entry["url"], timeout=60) as response:
                data = response.read(entry["bytes"] + 1)
            if (
                len(data) != entry["bytes"]
                or hashlib.sha256(data).hexdigest() != entry["sha256"]
            ):
                raise ValueError("Raw checksum mismatch")
            path.write_bytes(data)
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("Raw checksum mismatch")
        return entry, path

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        sources = list(pool.map(fetch, lock["files"]))
    counts = Counter()
    seen = set()
    groups = set()
    rejected = []
    rows = []
    raw_count = 0
    for entry, path in sources:
        for original in pq.read_table(path).to_pylist():
            raw_count += 1
            answers = original["answers"]
            if not answers["text"] or any(
                offset < 0 or original["context"][offset : offset + len(text)] != text
                for text, offset in zip(
                    answers["text"], answers["answer_start"], strict=True
                )
            ):
                rejected.append(
                    {
                        "language": entry["language"],
                        "id": original["id"],
                        "reason": "source_span_mismatch",
                    }
                )
                continue
            prompt = (
                "Passage:\n"
                + original["context"]
                + "\n\nQuestion: "
                + original["question"]
                + "\n\nReturn only the answer span from the passage."
            )
            digest = hashlib.sha256(prompt.encode()).hexdigest()
            if digest in seen:
                rejected.append(
                    {
                        "language": entry["language"],
                        "id": original["id"],
                        "reason": "exact_prompt_duplicate",
                    }
                )
                continue
            seen.add(digest)
            group = hashlib.sha256(("xquad:" + original["id"]).encode()).hexdigest()
            groups.add(group)
            record = DataRecord(
                id="xquad:" + entry["language"] + ":" + original["id"],
                dataset="xquad_" + entry["language"],
                family="xquad",
                source_split="validation",
                partition="evaluation",
                group_id=group,
                prompt=prompt,
                reference=Reference(
                    kind="span", alternatives=list(dict.fromkeys(answers["text"]))
                ),
                scorer="span_v1",
                license=lock["license"],
                source={
                    "repository": lock["repository"],
                    "revision": lock["revision"],
                    "configuration": entry["language"],
                    "source_id": original["id"],
                },
                metadata={
                    "language": entry["language"],
                    "evaluation_only": True,
                    "translation_group": original["id"],
                    "official_multilingual_scoring_validated": False,
                    "framing": "English instruction around original-language passage/question",
                },
            )
            rows.append(record.model_dump_json())
            counts[entry["language"]] += 1
    output = folder / "evaluation.jsonl"
    data = ("\n".join(rows) + "\n").encode()
    if output.exists() and output.read_bytes() != data:
        raise ValueError("Prepared export drift; version replacement")
    output.write_bytes(data)
    report = {
        "version": "xquad-v1",
        "source_rows": raw_count,
        "records": len(rows),
        "languages": dict(sorted(counts.items())),
        "translation_groups": len(groups),
        "family_count": 1,
        "quarantine": rejected,
        "path": str(output.relative_to(ROOT)),
        "sha256": hashlib.sha256(data).hexdigest(),
        "license": lock["license"],
        "license_basis": "Pinned dataset-card YAML; body licensing section is unspecified, not independent legal verification",
        "scope": "Evaluation-only translations of SQuAD v1.1; not independent of SQuAD data or independent tasks across languages",
        "status": "Prepared and reference-validated; no model runs or official multilingual scores",
        "limitations": [
            "Keep all translation groups evaluation-only; never train a policy on these overlapping public QA examples.",
            "English-focused span_v1 normalization is not a validated official multilingual scorer.",
            "No model pretraining holdout claim; no semantic near-duplicate guarantee.",
            "Original source data remain local and outside code packages.",
        ],
    }
    target = ROOT / "benchmarks/datasets/manifests/xquad-v1.json"
    if target.exists() and json.loads(target.read_text()) != report:
        raise ValueError("Manifest drift")
    target.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: report[k]
                for k in ["records", "languages", "translation_groups", "source_rows"]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    prepare()

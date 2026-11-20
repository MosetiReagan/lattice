"""Freeze and evaluate multilingual extractive QA using Unicode exact match."""

import asyncio
import hashlib
import json
import unicodedata
from collections import defaultdict

import quality_baseline as baseline

from lattice.config import file_hash
from lattice.data.schema import DataRecord
from lattice.data.scoring import Score

ROOT = baseline.ROOT
SUBSET = ROOT / "benchmarks/datasets/multilingual-subset-v1.json"


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def score_span(record: DataRecord, output: str) -> Score:
    references = record.reference.alternatives
    if record.reference.kind != "span" or not references:
        return Score("invalid_reference", None, None)
    return Score(
        "scored",
        normalize(output) in {normalize(text) for text in references},
        output.strip() in references,
    )


def freeze():
    spec = {
        "selection": "Eight cases per source language, ranked with SHA-256 seed 84721. One record per source group in each language.",
        "datasets": [],
    }
    caps = {}
    for name in ("tydiqa", "xquad"):
        manifest = json.loads(
            (ROOT / f"benchmarks/datasets/manifests/{name}-v1.json").read_text()
        )
        source = ROOT / manifest["path"]
        if file_hash(source) != manifest["sha256"]:
            raise ValueError("Prepared export checksum mismatch")
        strata = defaultdict(list)
        with source.open() as stream:
            for line in stream:
                record = DataRecord.model_validate_json(line)
                if record.partition != "evaluation":
                    raise ValueError("Expected evaluation partition")
                strata[record.metadata["language"]].append(record)
                caps[record.dataset] = 64
        selected = []
        for language, records in sorted(strata.items()):
            groups = set()
            for record in sorted(
                records, key=lambda r: hashlib.sha256(f"84721:{r.id}".encode()).digest()
            ):
                if record.group_id in groups:
                    continue
                groups.add(record.group_id)
                selected.append(
                    {
                        "id": record.id,
                        "stratum": language,
                        "prompt_sha256": record.prompt_sha256(),
                        "reference_sha256": record.reference_sha256(),
                    }
                )
                if len(groups) == 8:
                    break
            if len(groups) != 8:
                raise ValueError(f"Insufficient groups for {name} {language}")
        spec["datasets"].append(
            {
                "source_file": manifest["path"],
                "source_sha256": manifest["sha256"],
                "selected": selected,
            }
        )
    if SUBSET.exists():
        if json.loads(SUBSET.read_text()) != spec:
            raise ValueError("Frozen subset changed")
    else:
        SUBSET.write_text(json.dumps(spec, indent=2) + "\n")
    return caps


if __name__ == "__main__":
    baseline.MODELS = [baseline.MODELS[0], "qwen2.5-1.5b-instruct-q8"]
    asyncio.run(baseline.main(subset_path=SUBSET, caps=freeze(), scorer=score_span))

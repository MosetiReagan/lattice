"""Resolve approved public dataset revisions/files without remote dataset code.

Run intentionally to create a new source lock; the downloader never resolves
moving revisions. Unknown-license sources are not enabled merely because public.
"""

import argparse
import concurrent.futures
import datetime
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = [
    (
        "squad_v2",
        "squad",
        "rajpurkar/squad_v2",
        "squad_v2",
        "CC-BY-SA-4.0",
        ["train", "validation"],
    ),
    ("gsm8k", "gsm8k", "openai/gsm8k", "main", "MIT", ["train", "test"]),
    (
        "arc_easy",
        "arc",
        "allenai/ai2_arc",
        "ARC-Easy",
        "CC-BY-SA-4.0",
        ["train", "validation", "test"],
    ),
    (
        "arc_challenge",
        "arc",
        "allenai/ai2_arc",
        "ARC-Challenge",
        "CC-BY-SA-4.0",
        ["train", "validation", "test"],
    ),
    ("boolq", "boolq", "google/boolq", "data", "CC-BY-SA-3.0", ["train", "validation"]),
    (
        "commonsense_qa",
        "commonsense_qa",
        "tau/commonsense_qa",
        "data",
        "MIT",
        ["train", "validation"],
    ),
    ("ifeval", "ifeval", "google/IFEval", "default", "Apache-2.0", ["train"]),
    (
        "humaneval",
        "humaneval",
        "openai/openai_humaneval",
        "openai_humaneval",
        "MIT",
        ["test"],
    ),
    (
        "mbpp",
        "mbpp",
        "google-research-datasets/mbpp",
        "full",
        "CC-BY-4.0",
        ["prompt", "train", "validation", "test"],
    ),
    (
        "wikitext2",
        "wikitext",
        "Salesforce/wikitext",
        "wikitext-2-raw-v1",
        "CC-BY-SA-3.0 OR GFDL",
        ["train", "validation", "test"],
    ),
]


def request_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Lattice-dataset-intake"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def resolve_repository(repository):
    metadata = request_json(
        "https://huggingface.co/api/datasets/" + repository + "?blobs=true"
    )
    revision = metadata["sha"]
    pinned = request_json(
        f"https://huggingface.co/api/datasets/{repository}/revision/{revision}?blobs=true"
    )
    return pinned


def main():
    parser = argparse.ArgumentParser(
        description="Discover a NEW lock for explicit licensing review, not reproduction"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "benchmarks/datasets/sources.lock.json"
    )
    args = parser.parse_args()
    path = args.output
    if path.exists():
        raise SystemExit(
            "Source lock exists; preserve it and explicitly version a replacement"
        )
    repositories = sorted({row[2] for row in CATALOG})
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        metadata = dict(
            zip(repositories, pool.map(resolve_repository, repositories), strict=True)
        )
    root = ROOT / "benchmarks/datasets"
    audit = root / "source_audit"
    audit.mkdir(exist_ok=True)
    collections = []
    for name, family, repository, config, license_name, splits in CATALOG:
        source = metadata[repository]
        revision = source["sha"]
        files = []
        for split in splits:
            file = (
                "ifeval_input_data.jsonl"
                if name == "ifeval"
                else f"{config}/{split}-00000-of-00001.parquet"
            )
            entry = next(
                item for item in source["siblings"] if item["rfilename"] == file
            )
            files.append(
                {
                    "split": split,
                    "path": file,
                    "size_bytes": entry["size"],
                    "expected_sha256": entry.get("lfs", {}).get("sha256"),
                    "git_blob_sha1": entry["blobId"],
                    "url": f"https://huggingface.co/datasets/{repository}/resolve/{revision}/{file}",
                }
            )
        card_url = (
            f"https://huggingface.co/datasets/{repository}/raw/{revision}/README.md"
        )
        with urllib.request.urlopen(card_url, timeout=30) as response:
            card = response.read()
        card_file = repository.replace("/", "--") + "--" + revision + "-card.txt"
        (audit / card_file).write_bytes(card)
        collections.append(
            {
                "id": name,
                "family": family,
                "repository": repository,
                "revision": revision,
                "configuration": config,
                "license": license_name,
                "license_basis": "Pinned dataset card"
                if name != "winogrande"
                else "Pinned upstream README explicitly distinguishes dataset CC-BY from code Apache-2.0; data license version unspecified",
                "source_card": {
                    "url": card_url,
                    "snapshot": "source_audit/" + card_file,
                    "sha256": hashlib.sha256(card).hexdigest(),
                },
                "files": files,
                "format": "jsonl" if name == "ifeval" else "parquet",
                "attribution": repository + " contributors; see pinned card/citations",
                "external_data_redistribution": "Not included in Lattice code packages; retain source terms and attribution",
            }
        )
    result = {
        "schema_version": 1,
        "created_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "collections": collections,
        "excluded": [
            {
                "repository": "allenai/winogrande",
                "reason": "Code Apache-2.0 is not the dataset license; upstream data CC-BY version unspecified",
            },
            {
                "repository": "allenai/openbookqa",
                "reason": "Dataset license unknown in source card",
            },
            {
                "repository": "Rowan/hellaswag",
                "reason": "HF card licensing unspecified; upstream repository returned HTTP 451 during intake",
            },
            {
                "repository": "allenai/social_i_qa",
                "reason": "HF card license absent and repository uses a remote-code loader; not enabled in this intake",
            },
            {
                "source": "unlabeled external test splits",
                "reason": "No invented gold labels: only listed labeled splits are collected",
            },
            {
                "source": "Winogrande nested training subsets and MBPP sanitized mirror",
                "reason": "Avoid counting overlapping configurations as independent data",
            },
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path)


if __name__ == "__main__":
    main()

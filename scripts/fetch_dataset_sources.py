"""Download only data files named by an immutable source lock; verify bytes.

Parquet/JSONL are read as data. No Hugging Face dataset Python or model code runs.
External data remain outside code packages and keep source-specific licensing.
"""

import argparse
import concurrent.futures
import datetime
import hashlib
import json
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024**2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(item):
    collection, file, folder = item
    destination = (
        folder / collection["id"] / collection["revision"] / Path(file["path"]).name
    )
    destination.parent.mkdir(parents=True, exist_ok=True)

    def verify(path):
        if path.stat().st_size != file["size_bytes"]:
            raise ValueError("Dataset size mismatch")
        sha256 = hashlib.sha256()
        sha1 = hashlib.sha1(b"blob " + str(file["size_bytes"]).encode() + b"\0")
        with path.open("rb") as source:
            for data in iter(lambda: source.read(4 * 1024**2), b""):
                sha256.update(data)
                sha1.update(data)
        if file["expected_sha256"]:
            if sha256.hexdigest() != file["expected_sha256"]:
                raise ValueError("Dataset SHA-256 mismatch")
        elif sha1.hexdigest() != file["git_blob_sha1"]:
            raise ValueError("Pinned Git blob mismatch")
        return sha256.hexdigest()

    if destination.exists():
        digest = verify(destination)
    else:
        temporary = destination.with_suffix(destination.suffix + ".partial")
        for attempt in range(3):
            try:
                request = urllib.request.Request(
                    file["url"], headers={"User-Agent": "Lattice-pinned-data-intake"}
                )
                with (
                    urllib.request.urlopen(request, timeout=60) as response,
                    temporary.open("wb") as out,
                ):
                    total = 0
                    while data := response.read(1024**2):
                        total += len(data)
                        if total > file["size_bytes"]:
                            raise ValueError("Dataset exceeded locked size")
                        out.write(data)
                digest = verify(temporary)
                temporary.replace(destination)
                break
            except (OSError, urllib.error.URLError):
                temporary.unlink(missing_ok=True)
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
    return {
        "collection": collection["id"],
        "family": collection["family"],
        "split": file["split"],
        "revision": collection["revision"],
        "path": str(destination.relative_to(ROOT)),
        "size_bytes": destination.stat().st_size,
        "sha256": digest,
        "canonical_url": file["url"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--lock", type=Path, default=ROOT / "benchmarks/datasets/sources.lock.json"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "benchmarks/datasets/external/sources"
    )
    args = parser.parse_args()
    lock = json.loads(args.lock.read_text())
    required = sum(
        file["size_bytes"]
        for collection in lock["collections"]
        for file in collection["files"]
    )
    if shutil.disk_usage(ROOT).free < required + 3 * 1024**3:
        raise SystemExit("Dataset intake requires 3 GiB free disk reserve")
    for collection in lock["collections"]:
        if len(collection["revision"]) != 40:
            raise SystemExit("Only immutable dataset revisions are accepted")
        card = ROOT / "benchmarks/datasets" / collection["source_card"]["snapshot"]
        if digest_file(card) != collection["source_card"]["sha256"]:
            raise SystemExit("Source card changed after licensing intake")
        if any(
            Path(file["path"]).suffix not in (".parquet", ".jsonl")
            for file in collection["files"]
        ):
            raise SystemExit("Remote executable loaders are not data artifacts")
    items = [
        (collection, file, args.output)
        for collection in lock["collections"]
        for file in collection["files"]
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(fetch, items))
    manifest = {
        "created_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "source_lock_sha256": digest_file(args.lock),
        "files": rows,
        "total_bytes": sum(row["size_bytes"] for row in rows),
        "remote_code_executed": False,
    }
    path = ROOT / "benchmarks/datasets/external/download-manifest.json"
    if path.exists():
        existing = json.loads(path.read_text())
        if (
            existing["source_lock_sha256"] != manifest["source_lock_sha256"]
            or existing["files"] != rows
        ):
            raise SystemExit(
                "Download manifest differs; preserve and version the previous intake"
            )
        manifest = (
            existing  # Idempotent verification preserves frozen provenance hashes.
        )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                "files": len(rows),
                "bytes": manifest["total_bytes"],
                "manifest": str(path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

"""Fetch a pinned external quality corpus. Requires optional pyarrow dependency.

Dataset attribution/terms remain separate from Lattice's license. The downloaded
Wikipedia-derived text is intentionally not committed or included in packages.
"""

import hashlib
import json
import urllib.request
from pathlib import Path

import pyarrow.parquet as pq

REVISION = "b08601e04326c79dfdd32d625aee71d232d685c3"
REPOSITORY = "Salesforce/wikitext"
FILENAME = "wikitext-2-raw-v1/test-00000-of-00001.parquet"
root = Path(__file__).resolve().parents[1]
folder = root / "benchmarks/datasets/external"
folder.mkdir(exist_ok=True)
url = f"https://huggingface.co/datasets/{REPOSITORY}/resolve/{REVISION}/{FILENAME}"
parquet = folder / "wikitext-2-test.parquet"
with urllib.request.urlopen(url, timeout=60) as reply:
    parquet.write_bytes(reply.read())
texts = pq.read_table(parquet)["text"].to_pylist()
text = "".join(texts)
corpus = folder / "wikitext-2-test.txt"
corpus.write_text(text)
metadata = {
    "repository": REPOSITORY,
    "revision": REVISION,
    "file": FILENAME,
    "url": url,
    "parquet_sha256": hashlib.sha256(parquet.read_bytes()).hexdigest(),
    "corpus_sha256": hashlib.sha256(corpus.read_bytes()).hexdigest(),
    "rows": len(texts),
    "construction": "concatenate text rows with no added separator",
    "license": ["CC-BY-SA-3.0", "GFDL"],
    "attribution": "WikiText (Merity et al.); underlying Wikipedia contributors; see upstream dataset card",
    "source_card": f"https://huggingface.co/datasets/{REPOSITORY}/blob/{REVISION}/README.md",
}
(folder / "wikitext-2-test.manifest.json").write_text(
    json.dumps(metadata, indent=2) + "\n"
)
print(corpus)

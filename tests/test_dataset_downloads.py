import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "fetch", ROOT / "scripts/fetch_dataset_sources.py"
)
fetcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetcher)


def artifact(tmp_path, content, lfs):
    raw = tmp_path / "original.jsonl"
    raw.write_bytes(content)
    collection = {"id": "unit", "family": "unit", "revision": "a" * 40}
    item = {
        "path": "data.jsonl",
        "split": "test",
        "size_bytes": len(content),
        "expected_sha256": hashlib.sha256(content).hexdigest() if lfs else None,
        "git_blob_sha1": hashlib.sha1(
            b"blob " + str(len(content)).encode() + b"\0" + content
        ).hexdigest(),
        "url": raw.as_uri(),
    }
    return collection, item


@pytest.mark.parametrize("lfs", [False, True])
def test_verified_download_reuse_and_corruption(tmp_path, lfs):
    original = fetcher.ROOT
    fetcher.ROOT = tmp_path
    try:
        collection, item = artifact(tmp_path, b'{"text":"source"}\n', lfs)
        first = fetcher.fetch((collection, item, tmp_path / "download"))
        second = fetcher.fetch((collection, item, tmp_path / "download"))
        assert first == second
        target = tmp_path / first["path"]
        assert json.loads(target.read_text()) == {"text": "source"}
        target.write_bytes(b"x" * item["size_bytes"])
        with pytest.raises(ValueError, match="mismatch"):
            fetcher.fetch((collection, item, tmp_path / "download"))
    finally:
        fetcher.ROOT = original


def test_oversized_source_never_published(tmp_path):
    collection, item = artifact(tmp_path, b"0123456789", True)
    item["size_bytes"] = 2
    with pytest.raises(ValueError, match="exceeded locked size"):
        fetcher.fetch((collection, item, tmp_path / "download"))
    assert not list((tmp_path / "download").rglob("*.jsonl"))
    assert not list((tmp_path / "download").rglob("*.partial"))

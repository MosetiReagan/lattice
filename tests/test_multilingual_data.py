"""Data-only integration checks; never evidence of model inference."""

import json
from pathlib import Path

import pytest

from lattice.config import file_hash
from lattice.data.schema import DataRecord

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", ["tydiqa", "xquad"])
def test_prepared_multilingual_provenance_and_counts(name):
    manifest = json.loads(
        (ROOT / f"benchmarks/datasets/manifests/{name}-v1.json").read_text()
    )
    path = ROOT / manifest["path"]
    if not path.exists():
        pytest.skip("Optional local external export; reproduce with documented recipe")
    assert file_hash(path) == manifest["sha256"]
    identifiers = set()
    counts = {}
    for line in path.read_text().splitlines():
        item = DataRecord.model_validate_json(line)
        assert item.partition == "evaluation"
        assert item.reference.alternatives
        assert item.id not in identifiers
        identifiers.add(item.id)
        language = item.metadata["language"]
        counts[language] = counts.get(language, 0) + 1
    assert len(identifiers) == manifest["records"]
    assert counts == manifest["languages"]


def test_xquad_translation_groups_are_not_independent_datasets():
    report = json.loads(
        (ROOT / "benchmarks/datasets/manifests/xquad-v1.json").read_text()
    )
    assert report["family_count"] == 1
    assert report["translation_groups"] < report["records"]
    assert len(report["languages"]) == 12

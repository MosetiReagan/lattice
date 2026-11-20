"""Regress accidental writes to the historical catalog from the curated CLI."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "auditor", ROOT / "scripts/audit_dataset_catalog.py"
)
auditor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auditor)


@pytest.mark.parametrize("curated", [False, True])
def test_default_catalog_destination_follows_view(tmp_path, monkeypatch, curated):
    target = tmp_path / "benchmarks/datasets"
    target.mkdir(parents=True)
    original = target / "catalog-v1.json"
    original.write_text("historical original")
    alternate = target / "catalog-curated-v1.json"
    alternate.write_text("historical curated")
    monkeypatch.setattr(auditor, "ROOT", tmp_path)
    report = {
        "prepared_records": 193630 if curated else 193641,
        "task_records": 192884 if curated else 192895,
        "article_documents": 746,
        "canonical_synthetic_references_checked": 10389 if curated else 10400,
    }
    monkeypatch.setattr(auditor, "audit", lambda paths: report)
    monkeypatch.setattr(auditor, "apply_license_errata", lambda report: None)
    monkeypatch.setattr(sys, "argv", ["audit"] + (["--curated"] if curated else []))
    auditor.main()
    selected = alternate if curated else original
    protected = original if curated else alternate
    assert json.loads(selected.read_text()) == report
    assert protected.read_text() == (
        "historical original" if curated else "historical curated"
    )


def test_license_conflict_overrides_catalog_not_historical_file_labels(
    tmp_path, monkeypatch
):
    folder = tmp_path / "benchmarks/datasets"
    folder.mkdir(parents=True)
    (folder / "license-errata-v1.json").write_bytes(
        (ROOT / "benchmarks/datasets/license-errata-v1.json").read_bytes()
    )
    monkeypatch.setattr(auditor, "ROOT", tmp_path)
    report = {
        "datasets": {
            "wikitext2": {"licenses": ["CC-BY-SA-3.0 OR GFDL"], "records": 746}
        }
    }
    auditor.apply_license_errata(report)
    item = report["datasets"]["wikitext2"]
    assert item["licenses"] == ["LicenseRef-WikiText-Upstream-Conflict"]
    assert item["historical_record_license_labels"] == ["CC-BY-SA-3.0 OR GFDL"]
    assert item["records"] == 746
    assert report["license_errata"]["sha256"]

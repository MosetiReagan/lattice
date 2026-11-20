import importlib.util
from pathlib import Path

from lattice.data.schema import DataRecord, Reference

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "curator", ROOT / "scripts/curate_lattice_datasets.py"
)
curator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(curator)


def inventory(removed):
    return DataRecord(
        id="unit",
        dataset="lattice_arithmetic",
        family="lattice_arithmetic",
        source_split="generated",
        partition="evaluation",
        group_id="unit",
        prompt=f"A storage room has 2 boxes, with 100 bolts per box. Workers remove {removed} bolts. How many bolts remain?",
        reference=Reference(kind="number", value=str(200 - removed)),
        scorer="number_v1",
        license="Apache-2.0",
        source={},
        metadata={"template": "inventory_word_problem"},
    )


def test_negative_physical_stock_is_quarantined_not_relabelled():
    record = inventory(201)
    original = record.model_dump()
    assert curator.issues(record) == [
        "physical_inventory_removal_exceeds_available_stock"
    ]
    assert record.model_dump() == original


def test_zero_and_positive_remaining_stock_are_valid():
    assert not curator.issues(inventory(200))
    assert not curator.issues(inventory(199))

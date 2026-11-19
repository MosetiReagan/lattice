import importlib.util
from pathlib import Path

from lattice.data.schema import DataRecord, Reference

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "freeze", ROOT / "scripts/freeze_dataset_eval.py"
)
selector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selector)


def choice(index, label):
    return DataRecord(
        id=str(index),
        dataset="test",
        family="test",
        source_split="test",
        partition="evaluation",
        group_id=str(index),
        prompt="q" + str(index),
        reference=Reference(kind="choice", value=label),
        scorer="choice_v1",
        license="MIT",
        source={},
        metadata={"choice_labels": ["A", "B"]},
    )


def test_selection_is_order_independent_and_balances_strata():
    records = [choice(i, "A" if i < 30 else "B") for i in range(40)]
    selected = selector.select(records, 20, 84721)
    reversed_selection = selector.select(list(reversed(records)), 20, 84721)
    assert [r.id for r in selected] == [r.id for r in reversed_selection]
    assert sum(r.reference.value == "A" for r in selected) == 10
    assert len({r.id for r in selected}) == 20


def test_selection_exhaustion_preserves_available_records():
    records = [choice(i, "A" if i < 3 else "B") for i in range(5)]
    selected = selector.select(records, 100, 84721)
    assert {r.id for r in selected} == {r.id for r in records}
    assert selector.select([], 10, 84721) == []


def test_seed_changes_selected_instances():
    records = [choice(i, "A") for i in range(40)]
    assert [r.id for r in selector.select(records, 10, 1)] != [
        r.id for r in selector.select(records, 10, 2)
    ]

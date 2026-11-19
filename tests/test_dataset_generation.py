import importlib.util
from collections import defaultdict
from pathlib import Path

from lattice.data.schema import DataRecord
from lattice.data.scoring import score_record

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "generator", ROOT / "scripts/generate_lattice_datasets.py"
)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def test_generator_reproducibility_stratification_and_gold(tmp_path):
    counts = {
        "arithmetic": 100,
        "structured": 120,
        "instructions": 120,
        "retrieval": 400,
    }
    # Generator manifests expect repo-relative paths; override root only for this test.
    (tmp_path / "src").symlink_to(ROOT / "src", target_is_directory=True)
    original = generator.ROOT
    generator.ROOT = tmp_path
    try:
        first, _ = generator.generate("unit", 73021, counts, tmp_path / "one")
        second, _ = generator.generate("unit", 73021, counts, tmp_path / "two")
    finally:
        generator.ROOT = original
    assert [f["sha256"] for f in first["files"]] == [
        f["sha256"] for f in second["files"]
    ]
    seen = set()
    coverage = defaultdict(lambda: defaultdict(set))
    for entry in first["files"]:
        for line in (tmp_path / entry["path"]).read_text().splitlines():
            item = DataRecord.model_validate_json(line)
            assert item.content_sha256() not in seen
            seen.add(item.content_sha256())
            key = (item.metadata["template"], item.metadata.get("nominal_rows_tier"))
            coverage[item.dataset][item.partition].add(key)
            result = score_record(item, item.metadata["canonical_response"])
            assert result.answer_correct and result.strict_correct
    for partitions in coverage.values():
        assert (
            partitions["development"]
            == partitions["validation"]
            == partitions["evaluation"]
        )


def test_retrieval_gold_independently_resolves_records():
    import random
    import re

    for index in range(100):
        prompt, reference, _, gold, metadata = generator.retrieval(
            random.Random(index), index, (2000, 4999)
        )
        body, question = prompt.split("\n\n", 1)
        ordinary = dict(re.findall(r"^(k[0-9a-f]+) = (\d+)$", body, re.MULTILINE))
        kind = metadata["template"]
        if kind == "single_key":
            key = re.search(r"belongs to (k[0-9a-f]+)", question)[1]
            expected = ordinary[key]
        elif kind == "one_hop_pointer":
            key = re.search(r"Follow pointer (k[0-9a-f]+)", question)[1]
            destination = re.search(r"pointer " + key + r" -> (k[0-9a-f]+)", body)[1]
            expected = ordinary[destination]
        elif kind == "missing_key":
            key = re.search(r"belongs to (absent[0-9a-f]+)", question)[1]
            assert key not in body
            expected = "UNANSWERABLE"
        else:
            key = re.search(r"For (k[0-9a-f]+)", question)[1]
            versions = [
                (int(v), value)
                for v, value in re.findall(r"version (\d+): " + key + r" = (\d+)", body)
            ]
            expected = max(versions)[1]
        assert reference.value == expected == gold


def test_arithmetic_gold_independent_recalculation():
    import random
    import re
    from fractions import Fraction

    for index in range(200):
        prompt, reference, _, gold, metadata = generator.arithmetic(
            random.Random(index), index, (2000, 4999)
        )
        kind = metadata["template"]
        if kind == "integer_binary":
            match = re.search(r"Compute (\d+) ([+*\-]) (\d+)", prompt)
            a, b = int(match[1]), int(match[3])
            expected = a + b if match[2] == "+" else a - b if match[2] == "-" else a * b
        elif kind == "linear_equation":
            a, b, c = map(
                int, re.search(r"Solve (\d+) \* x \+ (\d+) = (\d+)", prompt).groups()
            )
            expected = Fraction(c - b, a)
        elif kind == "rational_addition":
            a, b, c, d = map(
                int, re.search(r"Compute (\d+)/(\d+) \+ (\d+)/(\d+)", prompt).groups()
            )
            expected = Fraction(a, b) + Fraction(c, d)
        elif kind == "inventory_word_problem":
            a, b, c = map(
                int,
                re.search(
                    r"has (\d+) boxes, with (\d+) bolts per box. Workers remove (\d+)",
                    prompt,
                ).groups(),
            )
            expected = a * b - c
        else:
            a, b = map(
                int,
                re.search(
                    r"Convert (\d+) large units.*?exactly (\d+) small", prompt
                ).groups(),
            )
            expected = a * b
        assert Fraction(reference.value) == expected == Fraction(gold)


def test_instruction_gold_and_mutations():
    import random

    for index in range(120):
        prompt, reference, scorer, gold, metadata = generator.instructions(
            random.Random(index), index, (2000, 4999)
        )
        item = DataRecord(
            id=str(index),
            dataset="test",
            family="test",
            source_split="generated",
            partition="evaluation",
            group_id=str(index),
            prompt=prompt,
            reference=reference,
            scorer=scorer,
            license="Apache-2.0",
            source={},
            metadata=metadata,
        )
        assert score_record(item, gold).strict_correct
        assert not score_record(item, "UNRELATED\n" + gold).strict_correct
        assert not score_record(item, gold + "\nUNRELATED").strict_correct

"""Generate deterministic, objectively labelled tasks without language-model gold.

These synthetic stress suites are not representative natural-language benchmarks.
Seeded numeric domains and instance identifiers remain disjoint; references are checked
with their declared scorer before a single record is emitted.
"""

import argparse
import datetime
import hashlib
import json
import random
import unicodedata
from collections import Counter
from fractions import Fraction
from pathlib import Path

from lattice.config import file_hash
from lattice.data.schema import DataRecord, Reference
from lattice.data.scoring import score_record

ROOT = Path(__file__).resolve().parents[1]
COUNTS = {
    "arithmetic": 4000,
    "structured": 2400,
    "instructions": 2400,
    "retrieval": 1600,
}
VOCAB = [
    "amber",
    "birch",
    "cedar",
    "delta",
    "elm",
    "fern",
    "gold",
    "hazel",
    "iris",
    "jade",
    "kelp",
    "lilac",
    "maple",
    "navy",
    "olive",
    "pearl",
    "quartz",
    "reed",
    "sage",
    "teal",
    "umber",
    "violet",
    "willow",
    "xenon",
    "yarrow",
    "zinc",
]


def canonical_number(value: Fraction | int) -> str:
    value = Fraction(value)
    return (
        str(value.numerator)
        if value.denominator == 1
        else f"{value.numerator}/{value.denominator}"
    )


def arithmetic(rng, index, domain):
    family = index % 5
    a = rng.randint(*domain)
    b = rng.randint(*domain)
    c = rng.randint(2, 19)
    if family == 0:
        op = rng.choice(["+", "-", "*"])
        value = {"+": a + b, "-": a - b, "*": a * b}[op]
        prompt = f"Compute {a} {op} {b}."
        kind = "integer_binary"
    elif family == 1:
        value = a
        prompt = f"Solve {c} * x + {b} = {c * a + b}. What is x?"
        kind = "linear_equation"
    elif family == 2:
        denominator = rng.randint(2, 37)
        value = Fraction(a, denominator) + Fraction(b, c)
        prompt = f"Compute {a}/{denominator} + {b}/{c}. Give a reduced fraction, or an integer if exact."
        kind = "rational_addition"
    elif family == 3:
        value = a * c - b
        prompt = f"A storage room has {c} boxes, with {a} bolts per box. Workers remove {b} bolts. How many bolts remain?"
        kind = "inventory_word_problem"
    else:
        factor = rng.choice([10, 100, 1000])
        value = a * factor
        prompt = f"Convert {a} large units to small units when each large unit is exactly {factor} small units."
        kind = "unit_conversion"
    gold = canonical_number(value)
    return (
        prompt + "\nReturn only the final number; use a reduced fraction if necessary.",
        Reference(kind="number", value=gold),
        "number_v1",
        gold,
        {"template": kind},
    )


def structured(rng, index, domain):
    family = index % 6
    identifier = f"item-{rng.getrandbits(48):012x}"
    name = rng.choice(VOCAB)
    value = rng.randint(*domain)
    if family == 0:
        gold = {"id": identifier, "name": name, "count": value}
        prompt = f"Record: id={identifier}; name={name}; count={value}. Return a JSON object with exactly id, name and count. count is an integer."
        kind = "record_extraction"
    elif family == 1:
        items = [
            {"name": f"{rng.choice(VOCAB)}-{i}", "count": rng.randint(0, 99)}
            for i in range(5)
        ]
        threshold = rng.randint(20, 80)
        gold = [
            r["name"]
            for r in sorted(items, key=lambda x: (x["count"], x["name"]))
            if r["count"] >= threshold
        ]
        prompt = (
            f"Input {identifier}: "
            + json.dumps(items)
            + f"\nReturn the names whose count is at least {threshold}, sorted by increasing count then name, as a JSON array."
        )
        kind = "filter_sort"
    elif family == 2:
        values = [rng.randint(-30, 90) for _ in range(6)]
        gold = {
            "id": identifier,
            "sum": sum(values),
            "minimum": min(values),
            "maximum": max(values),
        }
        prompt = (
            f"Input {identifier}: "
            + json.dumps(values)
            + "\nReturn a JSON object with id, sum, minimum and maximum."
        )
        kind = "array_aggregate"
    elif family == 3:
        enabled = rng.choice([True, False])
        gold = {"id": identifier, "enabled": enabled, "missing": None, "count": value}
        prompt = f"Return JSON for id {identifier}, enabled {str(enabled).lower()}, missing null, and integer count {value}. Preserve JSON types and use exactly these four keys."
        kind = "type_preservation"
    elif family == 4:
        text = rng.choice(
            [
                'quote " inside',
                "backslash \\ path",
                "snow 雪",
                "tab\tinside",
                "line\ninside",
            ]
        )
        gold = {"id": identifier, "text": text}
        prompt = (
            f"Create a JSON object with id {identifier}. Its text value is the following string represented as JSON: "
            + json.dumps(text, ensure_ascii=False)
            + ". Escape it correctly."
        )
        kind = "escaping_unicode"
    else:
        pairs = [(rng.choice(VOCAB), rng.randint(0, 20)) for _ in range(5)]
        totals = {}
        for key, amount in pairs:
            totals[key] = totals.get(key, 0) + amount
        gold = {"id": identifier, "totals": totals}
        prompt = (
            f"Input {identifier}: "
            + json.dumps(pairs)
            + "\nSum amounts by name. Return a JSON object with id and totals (an object mapping each name to its sum)."
        )
        kind = "nested_group_sum"
    return (
        prompt + "\nReturn valid JSON only, without Markdown or explanation.",
        Reference(kind="json", value=gold),
        "json_v1",
        json.dumps(gold, ensure_ascii=False, separators=(",", ":")),
        {"template": kind, "strict_json_required": True},
    )


def instructions(rng, index, domain):
    family = index % 6
    tag = f"{rng.getrandbits(48):012x}"
    words = rng.sample(VOCAB, 6)
    if family == 0:
        gold = "READY_" + tag.upper()
        checks = [{"type": "exact_text", "value": gold}]
        prompt = f"Reply with exactly READY_{tag.upper()} and nothing else."
        kind = "literal_case"
    elif family == 1:
        count = rng.randint(2, 5)
        gold = " ".join(words[:count])
        checks = [
            {"type": "exact_text", "value": gold},
            {"type": "word_count", "minimum": count, "maximum": count},
            {"type": "lowercase"},
        ]
        prompt = (
            f"Task {tag}: words = "
            + ", ".join(words)
            + f". Reply with only the first {count} words, in order, separated by single spaces, all lowercase."
        )
        kind = "word_count_case"
    elif family == 2:
        count = rng.randint(2, 4)
        gold = "\n".join(f"{i + 1}. {word}" for i, word in enumerate(words[:count]))
        checks = [
            {"type": "exact_text", "value": gold},
            {"type": "line_count", "count": count},
        ]
        prompt = (
            f"Task {tag}: output these words as {count} numbered nonempty lines, using 1. then 2. and so on, with no other lines: "
            + ", ".join(words[:count])
        )
        kind = "numbered_lines"
    elif family == 3:
        gold = "BEGIN_" + tag + "\n" + words[0] + " " + words[1] + "\nEND_" + tag
        checks = [
            {"type": "exact_text", "value": gold},
            {"type": "starts_with", "value": "BEGIN_" + tag},
            {"type": "ends_with", "value": "END_" + tag},
            {"type": "line_count", "count": 3},
            {"type": "required_keywords", "values": words[:2], "whole_words": True},
        ]
        prompt = f"Reply in exactly three nonempty lines: first BEGIN_{tag}; second the words {words[0]} {words[1]}; third END_{tag}. No extra text."
        kind = "header_footer"
    elif family == 4:
        required = words[0]
        forbidden = words[1]
        count = rng.randint(2, 4)
        gold = " ".join([required] * count)
        checks = [
            {"type": "exact_text", "value": gold},
            {"type": "keyword_frequency", "value": required, "count": count},
            {"type": "forbidden_keywords", "values": [forbidden], "whole_words": True},
            {"type": "word_count", "minimum": count, "maximum": count},
        ]
        prompt = f"Task {tag}: reply with exactly {count} whitespace-separated words. Every word must be {required}; do not include {forbidden}."
        kind = "frequency_forbidden"
    else:
        gold = json.dumps({"tag": tag, "ok": True}, separators=(",", ":"))
        checks = [{"type": "json_value", "value": {"tag": tag, "ok": True}}]
        prompt = f'Reply only with a JSON object containing exactly tag="{tag}" and ok=true. Use a JSON boolean, not a string.'
        kind = "json_constraint"
    return (
        prompt,
        Reference(kind="constraints", checks=checks),
        "constraints_v1",
        gold,
        {
            "template": kind,
            "constraint_definition": "Whitespace-separated words and nonempty lines; no official IFEval claim",
        },
    )


def retrieval(rng, index, domain):
    rows = [16, 32, 64, 128, 256][index % 5]
    family = (index // 5) % 4
    keys = [f"k{rng.getrandbits(48):012x}" for _ in range(rows)]
    values = [str(rng.randint(*domain)) for _ in keys]
    selected = rng.randrange(rows)
    key = keys[selected]
    if family == 0:
        entries = [f"{k} = {v}" for k, v in zip(keys, values, strict=True)]
        question = f"What exact value belongs to {key}?"
        gold = values[selected]
        kind = "single_key"
    elif family == 1:
        next_key = keys[(selected + 1) % rows]
        entries = [f"{k} = {v}" for k, v in zip(keys, values, strict=True)]
        entries.append(f"pointer {key} -> {next_key}")
        question = (
            f"Follow pointer {key}, then return the value of its destination key."
        )
        gold = values[(selected + 1) % rows]
        kind = "one_hop_pointer"
    elif family == 2:
        missing = f"absent{rng.getrandbits(48):012x}"
        entries = [f"{k} = {v}" for k, v in zip(keys, values, strict=True)]
        question = f"What value belongs to {missing}?"
        gold = "UNANSWERABLE"
        kind = "missing_key"
    else:
        old = values[selected]
        new = str(int(old) + rng.randint(1, 100))
        entries = [f"version 1: {k} = {v}" for k, v in zip(keys, values, strict=True)]
        entries.insert(rng.randrange(len(entries) + 1), f"version 2: {key} = {new}")
        question = f"For {key}, return the value from the highest numbered version, regardless of row order."
        gold = new
        kind = "versioned_override"
    rng.shuffle(entries)
    prompt = (
        "Records:\n"
        + "\n".join(entries)
        + "\n\n"
        + question
        + "\nReturn only the exact value. If it is absent, return exactly UNANSWERABLE."
    )
    return (
        prompt,
        Reference(kind="text", value=gold),
        "text_v1",
        gold,
        {
            "template": kind,
            "context_rows": len(entries),
            "nominal_rows_tier": rows,
            "token_length": "Must be measured per tokenizer; no invented token counts",
            "answerable": gold != "UNANSWERABLE",
        },
    )


GENERATORS = {
    "arithmetic": arithmetic,
    "structured": structured,
    "instructions": instructions,
    "retrieval": retrieval,
}


def generate(version: str, seed: int, counts: dict, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    files = []
    samples = {}
    all_prompts = set()
    all_groups = set()
    for dataset, count in counts.items():
        handles = {}
        counter = Counter()
        templates = Counter()
        sample = []
        try:
            for index in range(count):
                strata = {
                    "arithmetic": 5,
                    "structured": 6,
                    "instructions": 6,
                    "retrieval": 20,
                }[dataset]
                bucket = (index // strata) % 20
                partition = (
                    "evaluation"
                    if bucket < 4
                    else ("validation" if bucket < 8 else "development")
                )
                domain = {
                    "development": (100, 999),
                    "validation": (1000, 1999),
                    "evaluation": (2000, 4999),
                }[partition]
                local_seed = int.from_bytes(
                    hashlib.sha256(
                        f"{seed}:{dataset}:{index}:{partition}".encode()
                    ).digest()[:8],
                    "big",
                )
                rng = random.Random(local_seed)
                for attempt in range(1000):
                    prompt, reference, scorer, gold, metadata = GENERATORS[dataset](
                        rng, index, domain
                    )
                    digest = hashlib.sha256(
                        " ".join(unicodedata.normalize("NFC", prompt).split()).encode()
                    ).hexdigest()
                    if digest not in all_prompts:
                        break
                else:
                    raise RuntimeError("Could not sample a unique prompt")
                identifier = f"lattice_{dataset}:{version}:{index:06d}"
                record = DataRecord(
                    id=identifier,
                    dataset="lattice_" + dataset,
                    family="lattice_" + dataset,
                    source_split="generated",
                    partition=partition,
                    group_id=hashlib.sha256(identifier.encode()).hexdigest(),
                    prompt=prompt,
                    reference=reference,
                    scorer=scorer,
                    license="Apache-2.0",
                    source={
                        "generator": "lattice-data-" + version,
                        "seed": seed,
                        "index": index,
                    },
                    metadata={
                        **metadata,
                        "canonical_response": gold,
                        "synthetic": True,
                        "foundation_model_holdout_claim": False,
                    },
                )
                result = score_record(record, gold)
                if (
                    result.status != "scored"
                    or not result.answer_correct
                    or not result.strict_correct
                ):
                    raise RuntimeError(
                        "Generator produced an invalid gold reference: " + identifier
                    )
                digest = record.content_sha256()
                if digest in all_prompts:
                    raise RuntimeError("Generated prompt collision")
                all_prompts.add(digest)
                if record.group_id in all_groups:
                    raise RuntimeError("Generated group collision")
                all_groups.add(record.group_id)
                if partition not in handles:
                    path = output / record.dataset / (partition + ".jsonl")
                    path.parent.mkdir(exist_ok=True)
                    handles[partition] = (path, path.open("w"))
                handles[partition][1].write(record.model_dump_json() + "\n")
                counter[partition] += 1
                templates[metadata["template"]] += 1
                if len(sample) < 12:
                    sample.append(record.model_dump())
        finally:
            for _, stream in handles.values():
                stream.close()
        for partition, (path, _) in handles.items():
            files.append(
                {
                    "dataset": "lattice_" + dataset,
                    "partition": partition,
                    "rows": counter[partition],
                    "path": str(path.relative_to(ROOT)),
                    "bytes": path.stat().st_size,
                    "sha256": file_hash(path),
                }
            )
        samples[dataset] = {"records": sample, "templates": dict(templates)}
    manifest = {
        "schema_version": 1,
        "version": version,
        "seed": seed,
        "created_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "files": files,
        "records": sum(counts.values()),
        "license": "Apache-2.0",
        "generator_sha256": file_hash(Path(__file__)),
        "scorer_sha256": file_hash(ROOT / "src/lattice/data/scoring.py"),
        "schema_sha256": file_hash(ROOT / "src/lattice/data/schema.py"),
        "gold_source": "Deterministic arithmetic/transform/constraint logic; no LLM gold",
        "gold_validation": "Every canonical response passed its declared answer and strict scorer before export",
        "split_contract": "60/20/20 per-template/tier buckets; numeric operand domains and seeded instance identifiers disjoint across partitions; templates are shared, not held out",
        "limitations": [
            "Synthetic templates, not representative natural task distributions",
            "Public recipe/seed, not a foundation-model contamination guarantee",
        ],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest, samples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="intake-v1")
    parser.add_argument("--seed", type=int, default=73021)
    args = parser.parse_args()
    output = ROOT / "benchmarks/datasets/generated" / args.version
    manifest, samples = generate(args.version, args.seed, COUNTS, output)
    sample_dir = ROOT / "benchmarks/datasets/examples"
    sample_dir.mkdir(exist_ok=True)
    for dataset, data in samples.items():
        (sample_dir / (dataset + "-v1.json")).write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        )
    print(
        json.dumps(
            {"records": manifest["records"], "manifest": str(output / "manifest.json")},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

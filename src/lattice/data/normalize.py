"""Explicit dataset adapters. Source answers are never inferred from a model."""

import hashlib
import json
import re
from collections.abc import Iterator
from pathlib import Path

from .schema import DataRecord, Reference


def stable_id(
    collection: str, split: str, index: int, source_id: str | int | None
) -> str:
    key = str(source_id) if source_id is not None else str(index)
    return collection + ":" + split + ":" + key


def initial_partition(split: str) -> str:
    return {
        "train": "development",
        "prompt": "development",
        "validation": "validation",
        "test": "evaluation",
    }[split]


def normalize_row(spec: dict, split: str, index: int, row: dict) -> DataRecord:
    collection = spec["id"]
    family = spec["family"]
    metadata = {}
    source_id = row.get("id", row.get("task_id", row.get("key")))
    if collection in ("arc_easy", "arc_challenge", "commonsense_qa"):
        question = row["question"]
        texts = row["choices"]["text"]
        labels = row["choices"]["label"]
        if (
            len(texts) != len(labels)
            or not 2 <= len(labels) <= 8
            or len(set(labels)) != len(labels)
        ):
            raise ValueError("Invalid source choice layout")
        if row["answerKey"] not in labels:
            raise ValueError("Missing or unrecognized source answer key")
        normalized = [chr(65 + i) for i in range(len(labels))]
        gold = normalized[labels.index(row["answerKey"])]
        prompt = (
            question
            + "\n\n"
            + "\n".join(
                f"{label}. {text}"
                for label, text in zip(normalized, texts, strict=True)
            )
        )
        prompt += "\n\nReply with only the letter of the best answer."
        reference = Reference(kind="choice", value=gold)
        scorer = "choice_v1"
        metadata = {
            "choice_labels": normalized,
            "original_choice_labels": labels,
            "choice_texts": texts,
            "protocol": "zero-shot generated choice, not likelihood-ranked official leaderboard protocol",
        }
        group_text = " ".join(question.split())
    elif collection == "gsm8k":
        if "####" not in row["answer"]:
            raise ValueError("GSM8K reference lacks final-answer delimiter")
        gold = row["answer"].rsplit("####", 1)[1].strip().replace(",", "")
        if not re.fullmatch(r"-?\d+(?:\.\d+)?", gold):
            raise ValueError("Unexpected GSM8K numeric gold")
        prompt = (
            row["question"]
            + "\n\nGive only the final numeric answer, without explanation."
        )
        reference = Reference(kind="number", value=gold)
        scorer = "number_v1"
        group_text = row["question"]
        metadata = {
            "source_rationale": row["answer"],
            "protocol": "zero-shot answer generation; rationale retained only in reference metadata",
        }
    elif collection == "boolq":
        if type(row["answer"]) is not bool:
            raise ValueError("BoolQ source label is not boolean")
        prompt = (
            "Passage:\n"
            + row["passage"]
            + "\n\nQuestion: "
            + row["question"]
            + "\n\nReply with only yes or no."
        )
        reference = Reference(kind="boolean", value=row["answer"])
        scorer = "boolean_v1"
        group_text = row["passage"]
        metadata = {"protocol": "passage-grounded generated yes/no"}
    elif collection == "squad_v2":
        answers = row["answers"]
        texts = answers["text"]
        starts = answers["answer_start"]
        if len(texts) != len(starts):
            raise ValueError("SQuAD span metadata lengths disagree")
        for text, start in zip(texts, starts, strict=True):
            if row["context"][start : start + len(text)] != text:
                raise ValueError("SQuAD answer span does not match its context")
        prompt = "Passage:\n" + row["context"] + "\n\nQuestion: " + row["question"]
        prompt += "\n\nReturn only the shortest answer from the passage. If the passage does not answer the question, return exactly UNANSWERABLE."
        reference = Reference(kind="span", alternatives=list(dict.fromkeys(texts)))
        scorer = "span_v1"
        metadata = {
            "answerable": bool(texts),
            "source_title": row["title"],
            "context_sha256": hashlib.sha256(row["context"].encode()).hexdigest(),
            "source_answer_starts": starts,
            "protocol": "generated span; explicit UNANSWERABLE maps to empty prediction",
        }
        # Keep related questions/article contexts together in policy splits.
        group_text = row["title"]
    elif collection == "ifeval":
        if len(row["instruction_id_list"]) != len(row["kwargs"]):
            raise ValueError("IFEval checks/kwargs mismatch")
        prompt = row["prompt"]
        reference = Reference(
            kind="constraints",
            checks=[
                {"instruction_id": key, "kwargs": kwargs}
                for key, kwargs in zip(
                    row["instruction_id_list"], row["kwargs"], strict=True
                )
            ],
        )
        scorer = "ifeval_official_deferred"
        metadata = {
            "official_verifier_required": True,
            "protocol": "raw official instructions; not a Lattice reimplementation of the official score",
        }
        group_text = prompt
    elif collection == "humaneval":
        prompt = (
            "Complete the following Python function. Return the complete Python code only.\n\n"
            + row["prompt"]
        )
        reference = Reference(
            kind="program",
            value={
                "prompt_prefix": row["prompt"],
                "canonical_solution": row["canonical_solution"],
                "test": row["test"],
                "entry_point": row["entry_point"],
            },
        )
        scorer = "code_execution_deferred"
        metadata = {
            "execution_required": True,
            "protocol": "full-code response adaptation; no pass@k without sandboxed execution",
        }
        group_text = row["prompt"]
    elif collection == "mbpp":
        prompt = (
            row["text"]
            + "\n\nReturn only Python code implementing the requested function.\nRequired public examples:\n"
            + "\n".join(row["test_list"])
        )
        reference = Reference(
            kind="program",
            value={
                "canonical_solution": row["code"],
                "test_list": row["test_list"],
                "test_setup_code": row.get("test_setup_code", ""),
                "challenge_test_list": row.get("challenge_test_list", []),
            },
        )
        scorer = "code_execution_deferred"
        metadata = {
            "execution_required": True,
            "public_tests_in_prompt": True,
            "protocol": "MBPP source public tests shown as examples; challenge tests remain reference-only",
        }
        group_text = row["text"]
    else:
        raise ValueError("No explicit adapter for " + collection)
    group = hashlib.sha256(
        (family + "\0" + " ".join(group_text.split())).encode()
    ).hexdigest()
    return DataRecord(
        id=stable_id(collection, split, index, source_id),
        dataset=collection,
        family=family,
        source_split=split,
        partition=initial_partition(split),
        group_id=group,
        prompt=prompt,
        reference=reference,
        scorer=scorer,
        license=spec["license"],
        source={
            "repository": spec["repository"],
            "revision": spec["revision"],
            "configuration": spec["configuration"],
            "split": split,
            "row": index,
            "source_id": source_id,
        },
        metadata=metadata,
    )


def wiki_documents(spec: dict, split: str, texts: list[str]) -> Iterator[DataRecord]:
    # WikiText rows are paragraph/fragments, not independent QA examples.
    chunks = []
    title = "preamble"
    index = 0

    def record():
        nonlocal index
        text = "".join(chunks)
        if not text.strip():
            return None
        item = DataRecord(
            id=f"wikitext2:{split}:article-{index}",
            dataset="wikitext2",
            family="wikitext",
            source_split=split,
            partition="corpus",
            group_id=hashlib.sha256(title.encode()).hexdigest(),
            prompt=text,
            reference=Reference(kind="document"),
            scorer="language_model_loss_deferred",
            license=spec["license"],
            source={
                "repository": spec["repository"],
                "revision": spec["revision"],
                "split": split,
                "article_index": index,
            },
            metadata={
                "title": title,
                "raw_text_preserved": True,
                "unit": "article",
                "protocol": "corpus loss, not generated-answer accuracy",
            },
        )
        index += 1
        return item

    for text in texts:
        if re.fullmatch(r"\s*= [^=\n].*? =\s*", text) and "\n" not in text.strip():
            if chunks:
                item = record()
                if item:
                    yield item
            chunks = []
            title = text.strip().strip("= ")
        chunks.append(text)
    if chunks:
        item = record()
        if item:
            yield item


def source_rows(path: Path) -> Iterator[dict]:
    if path.suffix == ".jsonl":
        with path.open() as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)
    elif path.suffix == ".parquet":
        import pyarrow.parquet as pq

        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(batch_size=2048):
            yield from batch.to_pylist()
    else:
        raise ValueError("Only locked JSONL/Parquet sources are supported")

"""Standard-generation quality audit on pre-frozen dataset IDs.

This is a dataset/scorer integration study, not an isolated latency benchmark.
No execution policy is trained or promoted. Code/official IFEval stay deferred.
"""

import argparse
import asyncio
import datetime
import json
import math
import platform
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import httpx

from lattice.backends import create_backend
from lattice.config import file_hash, load_settings, select_model
from lattice.data.schema import DataRecord
from lattice.data.scoring import score_record
from lattice.evaluation.benchmark import source_manifest
from lattice.optimizations.speculative.compatibility import tokenizer_fingerprint
from lattice.runtime import Runtime
from lattice.types import GenerationRequest, LatticeError, Message

ROOT = Path(__file__).resolve().parents[2]
MODELS = [
    "qwen2.5-0.5b-instruct-f16",
    "qwen2.5-0.5b-instruct-q8_0",
    "qwen2.5-0.5b-instruct-q4_k_m",
]
CAPS = {
    "arc_easy": 8,
    "arc_challenge": 8,
    "boolq": 8,
    "commonsense_qa": 8,
    "gsm8k": 96,
    "squad_v2": 48,
    "lattice_arithmetic": 64,
    "lattice_structured": 192,
    "lattice_instructions": 96,
    "lattice_retrieval": 32,
}


def wilson(correct, n):
    if not n:
        return None
    z = 1.959963984540054
    p = correct / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [max(0.0, center - half), min(1.0, center + half)]


def summarize(rows):
    by_dataset = defaultdict(list)
    for row in rows:
        by_dataset[row["dataset"]].append(row)
    result = {}
    for dataset, items in by_dataset.items():
        completed = [r for r in items if r["status"] == "completed"]
        scored = [r for r in completed if r["score"]["status"] == "scored"]
        n = len(scored)
        answer = sum(r["score"]["answer_correct"] for r in scored)
        strict = sum(r["score"]["strict_correct"] for r in scored)
        result[dataset] = {
            "selected": len(items),
            "completed": len(completed),
            "scored": n,
            "excluded": len(items) - n,
            "answer_correct": answer,
            "strict_correct": strict,
            "answer_accuracy": answer / n if n else None,
            "strict_accuracy": strict / n if n else None,
            "answer_wilson95": wilson(answer, n),
            "truncated_completions": sum(
                r.get("finish_reason") == "length" for r in completed
            ),
            "operational_seconds": sum(r.get("operational_seconds", 0) for r in items),
            "by_stratum": {},
        }
        for stratum in sorted({r["stratum"] for r in items}):
            subset = [r for r in scored if r["stratum"] == stratum]
            result[dataset]["by_stratum"][stratum] = {
                "scored": len(subset),
                "answer_correct": sum(r["score"]["answer_correct"] for r in subset),
                "strict_correct": sum(r["score"]["strict_correct"] for r in subset),
            }
        f1 = [
            r["score"]["metrics"]["token_f1"]
            for r in scored
            if "token_f1" in r["score"]["metrics"]
        ]
        if f1:
            result[dataset]["span_token_f1"] = sum(f1) / len(f1)
    return result


async def tokenize(backend, client, prompt):
    response = await backend._post(
        client, "/apply-template", {"messages": [{"role": "user", "content": prompt}]}
    )
    rendered = response["prompt"]
    response = await backend._post(
        client,
        "/tokenize",
        {"content": rendered, "add_special": True, "parse_special": True},
    )
    return len(response["tokens"])


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "benchmarks/results/dataset-quality-v1"
    )
    parser.add_argument("--wait-for-corpus", action="store_true")
    args = parser.parse_args()
    if args.wait_for_corpus:
        while not (
            ROOT / "benchmarks/results/dataset-intake-full-corpus-v1/summary.json"
        ).exists():
            await asyncio.sleep(5)
    args.output.mkdir(parents=True, exist_ok=False)
    subset_path = ROOT / "benchmarks/datasets/eval-subsets-v1.json"
    frozen = json.loads(subset_path.read_text())
    tasks = []
    for dataset in frozen["datasets"]:
        path = ROOT / dataset["source_file"]
        if file_hash(path) != dataset["source_sha256"]:
            raise RuntimeError("Evaluation dataset checksum changed")
        wanted = {s["id"]: s for s in dataset["selected"]}
        rows = {
            r.id: r
            for line in path.read_text().splitlines()
            if (r := DataRecord.model_validate_json(line)).id in wanted
        }
        for row in dataset["selected"]:
            record = rows[row["id"]]
            if (
                record.prompt_sha256() != row["prompt_sha256"]
                or record.reference_sha256() != row["reference_sha256"]
            ):
                raise RuntimeError("Frozen prompt/reference changed")
            tasks.append((record, row["stratum"]))
    settings = load_settings()
    settings.native_slots = 1
    settings.context_tokens = 2048
    manifest = {
        "created_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "source_manifest": source_manifest(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "threads": settings.threads,
        "worker_address_space_mb": settings.worker_address_space_mb,
        "host_reserve_mb": settings.host_reserve_mb,
        "frozen_subset_sha256": file_hash(subset_path),
        "scorer_sha256": file_hash(ROOT / "src/lattice/data/scoring.py"),
        "runner_sha256": file_hash(Path(__file__)),
        "backend_sha256": settings.backend_sha256,
        "backend_commit": settings.backend_commit,
        "strategy": "standard",
        "precision_selection": "Explicit fixed model per run; no routing, cache mode or speculative decoding",
        "temperature": 0.0,
        "seed": 84721,
        "context_tokens": 2048,
        "native_slots": 1,
        "output_caps": CAPS,
        "timing_scope": "Operational only; no speed comparison",
        "protocol": "Zero-shot user chat, generated answers; not official leaderboard scores",
        "selection": frozen["selection"],
        "oversize_policy": "Skip explicitly without truncation; paired model denominators must agree",
        "truncation_policy": "Length-limited generated outputs remain scored, never discarded",
        "models": {},
    }
    summary = {}
    fingerprints = set()
    for model_id in MODELS:
        entry = select_model(settings, model_id)
        if file_hash(Path(entry.path)) != entry.sha256:
            raise RuntimeError("Model checksum changed")
        fingerprint = tokenizer_fingerprint(Path(entry.path))
        fingerprints.add(fingerprint)
        if len(fingerprints) != 1:
            raise RuntimeError("Precision variants changed tokenizer")
        manifest["models"][model_id] = {
            "sha256": entry.sha256,
            "source_repository": entry.source_repository,
            "source_revision": entry.source_revision,
            "license": entry.license,
            "tokenizer_fingerprint": fingerprint,
            "precision": entry.precision,
        }
        (args.output / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n"
        )
        backend = create_backend(settings, entry)
        runtime = Runtime(settings, model_id, backend)
        rows = []
        try:
            await backend.start()
            async with httpx.AsyncClient(
                base_url=backend.base_url,
                headers=backend.headers,
                timeout=60,
                trust_env=False,
            ) as client:
                with (args.output / (model_id + ".jsonl")).open("w") as stream:
                    for record, stratum in tasks:
                        started = time.monotonic()
                        row = {
                            "id": record.id,
                            "dataset": record.dataset,
                            "stratum": stratum,
                            "prompt_sha256": record.prompt_sha256(),
                            "reference_sha256": record.reference_sha256(),
                            "license": record.license,
                            "source": record.source,
                            "max_tokens": CAPS[record.dataset],
                        }
                        try:
                            prompt_tokens = await tokenize(
                                backend, client, record.prompt
                            )
                            row["prompt_tokens"] = prompt_tokens
                            if (
                                len(record.prompt.encode()) > 32768
                                or prompt_tokens + CAPS[record.dataset]
                                > settings.context_tokens
                            ):
                                row.update(status="skipped_context_limit", score=None)
                            else:
                                request = GenerationRequest(
                                    model=model_id,
                                    messages=[
                                        Message(role="user", content=record.prompt)
                                    ],
                                    max_tokens=CAPS[record.dataset],
                                    temperature=0.0,
                                    seed=84721,
                                    timeout_seconds=120.0,
                                )
                                result = await runtime.generate(request)
                                row.update(
                                    status="completed",
                                    text=result["text"],
                                    score=asdict(score_record(record, result["text"])),
                                    completion_tokens=result["metadata"][
                                        "completion_tokens"
                                    ],
                                    finish_reason=result["metadata"]["finish_reason"],
                                    selected_strategy=result["metadata"]["strategy"],
                                )
                        except LatticeError as exc:
                            row.update(
                                status="error",
                                error_code=exc.code,
                                error=str(exc),
                                score=None,
                            )
                        row["operational_seconds"] = time.monotonic() - started
                        rows.append(row)
                        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                        stream.flush()
                        if len(rows) % 20 == 0:
                            print(model_id, len(rows), "/", len(tasks), flush=True)
                            (args.output / "progress.json").write_text(
                                json.dumps(
                                    {
                                        "model": model_id,
                                        "processed": len(rows),
                                        "total": len(tasks),
                                        "datasets": summarize(rows),
                                    },
                                    indent=2,
                                )
                                + "\n"
                            )
        finally:
            backend.stop()
        summary[model_id] = summarize(rows)
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.output / "completed.json").write_text(
        json.dumps(
            {
                "models": MODELS,
                "records_per_model": len(tasks),
                "completed_utc": datetime.datetime.now(datetime.UTC).isoformat(),
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    asyncio.run(main())

"""Additional fixed 8k-context retrieval observations on the frozen 60 cases.

Preserves the 2k baseline and all its honest skips. This is a different context
configuration, not proof of a latency optimization or broad long-context ability.
"""

import argparse
import asyncio
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

from lattice.backends import create_backend
from lattice.config import file_hash, load_settings, select_model
from lattice.data.schema import DataRecord
from lattice.data.scoring import score_record
from lattice.evaluation.benchmark import source_manifest
from lattice.runtime import Runtime
from lattice.types import GenerationRequest, LatticeError, Message

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "benchmarks/results/dataset-long-context-v1"
MODEL = "qwen2.5-0.5b-instruct-f16"


async def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    OUT = args.output
    while not (
        ROOT / "benchmarks/results/dataset-intake-1.5b-corpus-subset-v1/summary.json"
    ).exists():
        await asyncio.sleep(5)
    OUT.mkdir(parents=True, exist_ok=False)
    frozen_path = ROOT / "benchmarks/datasets/eval-subsets-curated-v1.json"
    frozen = json.loads(frozen_path.read_text())
    selection = next(
        d for d in frozen["datasets"] if d["dataset"] == "lattice_retrieval"
    )
    path = ROOT / selection["source_file"]
    if file_hash(path) != selection["source_sha256"]:
        raise ValueError("Retrieval source changed")
    wanted = {r["id"]: r for r in selection["selected"]}
    records = {
        r.id: r
        for line in path.read_text().splitlines()
        if (r := DataRecord.model_validate_json(line)).id in wanted
    }
    settings = load_settings()
    settings.native_slots = 1
    settings.context_tokens = 8192
    entry = select_model(settings, MODEL)
    if file_hash(Path(entry.path)) != entry.sha256:
        raise ValueError("Model artifact changed")
    manifest = {
        "model": MODEL,
        "model_sha256": entry.sha256,
        "backend_commit": settings.backend_commit,
        "backend_sha256": settings.backend_sha256,
        "source_manifest": source_manifest(),
        "runner_sha256": file_hash(Path(__file__)),
        "frozen_subset_sha256": file_hash(frozen_path),
        "scorer_sha256": file_hash(ROOT / "src/lattice/data/scoring.py"),
        "context_tokens": 8192,
        "max_output_tokens": 32,
        "temperature": 0.0,
        "seed": 84721,
        "native_slots": 1,
        "threads": settings.threads,
        "strategy": "standard",
        "scope": "Additional explicit 8k-context CPU configuration, frozen retrieval only; original 2k baseline and skips preserved; no latency/memory/quality-preservation claim",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    backend = create_backend(settings, entry)
    runtime = Runtime(settings, MODEL, backend)
    rows = []
    try:
        with (OUT / "outcomes.jsonl").open("w") as output:
            for selected in selection["selected"]:
                record = records[selected["id"]]
                if (
                    record.prompt_sha256() != selected["prompt_sha256"]
                    or record.reference_sha256() != selected["reference_sha256"]
                ):
                    raise ValueError("Frozen retrieval case changed")
                row = {
                    "id": record.id,
                    "prompt_sha256": record.prompt_sha256(),
                    "reference_sha256": record.reference_sha256(),
                    "nominal_rows_tier": record.metadata["nominal_rows_tier"],
                    "template": record.metadata["template"],
                    "source_license": record.license,
                }
                try:
                    result = await runtime.generate(
                        GenerationRequest(
                            model=MODEL,
                            messages=[Message(role="user", content=record.prompt)],
                            max_tokens=32,
                            temperature=0.0,
                            seed=84721,
                            timeout_seconds=120.0,
                        )
                    )
                    if result["metadata"]["strategy"] != "standard":
                        raise ValueError("Unexpected optimization path")
                    row.update(
                        status="completed",
                        text=result["text"],
                        score=asdict(score_record(record, result["text"])),
                        prompt_tokens=result["metadata"]["prompt_tokens"],
                        completion_tokens=result["metadata"]["completion_tokens"],
                        finish_reason=result["metadata"]["finish_reason"],
                    )
                except LatticeError as exc:
                    row.update(
                        status="error", error_code=exc.code, error=str(exc), score=None
                    )
                rows.append(row)
                output.write(json.dumps(row) + "\n")
                output.flush()
                print(
                    "8k retrieval",
                    len(rows),
                    "/",
                    len(selection["selected"]),
                    flush=True,
                )
    finally:
        backend.stop()
    tiers = defaultdict(list)
    for row in rows:
        tiers[row["nominal_rows_tier"]].append(row)
    summary = {
        "selected": len(rows),
        "statuses": dict(Counter(r["status"] for r in rows)),
        "model": MODEL,
        "context_tokens": 8192,
        "outcomes_sha256": file_hash(OUT / "outcomes.jsonl"),
        "tiers": {},
    }
    for tier, items in sorted(tiers.items()):
        scored = [
            r
            for r in items
            if r["status"] == "completed" and r["score"]["status"] == "scored"
        ]
        summary["tiers"][tier] = {
            "selected": len(items),
            "scored": len(scored),
            "answer_correct": sum(r["score"]["answer_correct"] for r in scored),
            "strict_correct": sum(r["score"]["strict_correct"] for r in scored),
            "output_cap_finishes": sum(r["finish_reason"] == "length" for r in scored),
            "minimum_prompt_tokens": min(
                (r["prompt_tokens"] for r in scored), default=None
            ),
            "maximum_prompt_tokens": max(
                (r["prompt_tokens"] for r in scored), default=None
            ),
        }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# Additional 8k-context retrieval observations",
        "",
        "This separate CPU run explicitly selects the same 0.5B FP16 weights with an **8,192-token context**, standard greedy inference, seed 84721 and a 32-token output cap. It uses all 60 previously frozen retrieval cases. The original 2k-context baseline and its 24 exclusions are preserved. Different context configurations and coverage must not be presented as a latency optimization or a quality-preserving substitution.",
        "",
        "| Nominal base rows | Selected | Scored | Exact correct | Prompt token range | Output-cap finishes |",
        "|---|---:|---:|---:|---|---:|",
    ]
    for tier, item in summary["tiers"].items():
        lines.append(
            f"| {tier} | {item['selected']} | {item['scored']} | {item['answer_correct']} | {item['minimum_prompt_tokens']}–{item['maximum_prompt_tokens']} | {item['output_cap_finishes']} |"
        )
    lines += [
        "",
        f"Status counts: `{json.dumps(summary['statuses'], sort_keys=True)}`. No input was truncated. Output-cap finishes remain scored; error cases are explicitly excluded from the scored denominator. Success means exact trimmed value/UNANSWERABLE compliance on this synthetic task, not broad long-context comprehension. Twelve cases per tier and shared templates cannot establish population quality guarantees.",
        "",
        "[Raw outputs and per-case scores](../benchmarks/results/dataset-long-context-v1/outcomes.jsonl), [configuration and hashes](../benchmarks/results/dataset-long-context-v1/manifest.json) and [summary](../benchmarks/results/dataset-long-context-v1/summary.json) preserve all failures. Row tiers are not token counts; pointer/override templates add a row. This run supports only this tested CPU/model/context configuration, not all models or accelerators. No speed, memory or energy claim is made.",
        "",
        "See [dataset cards](datasets.md) and [the original precision study](dataset_results.md).",
        "",
    ]
    (ROOT / "docs/long_context_dataset_results.md").write_text("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())

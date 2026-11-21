"""Predeclared post-confirmation boundaries; these never tune the candidate."""

import asyncio
import hashlib
import json
import os
from pathlib import Path

import httpx
from burst_admission import MODEL, make_trace, run_trace

from lattice.backends.http_client import native_ssl_context
from lattice.backends.llama_cpp import LlamaCppBackend
from lattice.config import file_hash, load_settings, select_model
from lattice.evaluation.benchmark import source_manifest
from lattice.observability.host import CpuStealSampler

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("interactive_only", 0, 12, 0.0),
    ("bulk_only", 6, 0, 0.0),
    ("mixed_25_percent_interactive", 9, 3, 0.03),
    ("mixed_75_percent_interactive", 3, 9, 0.03),
    ("interactive_arrives_late", 6, 6, 0.15),
]


async def main():
    protocol_path = ROOT / "benchmarks/workloads/chat-burst-confirmation-v1.json"
    protocol = json.loads(protocol_path.read_text())
    output = ROOT / "benchmarks/results/chat-admission-boundaries-v1"
    output.mkdir(parents=True, exist_ok=False)
    settings = load_settings()
    settings.log_directory = str(output / "private" / "template-preparation")
    backend = LlamaCppBackend(settings, select_model(settings, MODEL))
    traces = []
    for index, (name, bulk, interactive, delay) in enumerate(CASES):
        trace = make_trace(15001 + index, bulk=bulk, interactive=interactive)
        for row in trace:
            if row["class"] == "interactive":
                row["arrival_seconds"] = (
                    delay + (int(row["id"].split("-")[-1]) - bulk) * 0.002
                )
        traces.append({"case": name, "requests": trace})
    try:
        await backend.start()
        async with httpx.AsyncClient(
            base_url=backend.base_url,
            headers=backend.headers,
            verify=native_ssl_context(),
            trust_env=False,
            timeout=30.0,
        ) as client:
            for case in traces:
                for row in case["requests"]:
                    response = await client.post(
                        "/apply-template",
                        json={"messages": [{"role": "user", "content": row["prompt"]}]},
                    )
                    response.raise_for_status()
                    row["raw_prompt_sha256"] = row["prompt_sha256"]
                    row["prompt"] = response.json()["prompt"]
                    row["prompt_sha256"] = hashlib.sha256(
                        row["prompt"].encode()
                    ).hexdigest()
    finally:
        backend.stop()
    arms = [protocol["baselines"][0], protocol["candidate"]]
    manifest = {
        "protocol_sha256": file_hash(protocol_path),
        "source": source_manifest(),
        "threads": settings.threads,
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "settings_sha256": file_hash(
            Path(os.environ.get("LATTICE_CONFIG", "configs/local.json"))
        ),
        "runner_sha256": file_hash(Path(__file__)),
        "arms": arms,
        "traces": traces,
        "stage": "Single-trace post-confirmation boundaries fixed before confirmation; no tuning, statistical qualification or replacement of primary results.",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    results = []
    with (output / "results.jsonl").open("x") as stream:
        for index, case in enumerate(traces):
            order = arms if index % 2 == 0 else list(reversed(arms))
            for arm in order:
                async with CpuStealSampler() as host_cpu:
                    result = await run_trace(arm, case["requests"], output)
                result["host_cpu"] = host_cpu.summary()
                result["case"] = case["case"]
                results.append(result)
                stream.write(json.dumps(result) + "\n")
                stream.flush()
                print(
                    case["case"],
                    arm,
                    result["tokens_per_second"],
                    "errors",
                    result["failures"],
                    flush=True,
                )
    (output / "summary.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main())

"""Bounded real-model probe before building concurrent-serving benchmarks."""

import asyncio
import json
from contextlib import aclosing
from pathlib import Path

from lattice.backends.batched import BatchedLlamaBackend
from lattice.config import load_settings
from lattice.runtime import Runtime
from lattice.types import GenerationRequest


async def main():
    settings = load_settings()
    settings.native_slots = 2
    settings.log_directory = "artifacts/concurrency-probe"
    backend = BatchedLlamaBackend(settings, settings.models[0])
    runtime = Runtime(settings, settings.models[0].id, backend)
    try:
        await backend.start()
        pid = backend.process.pid
        started = asyncio.Event()

        async def long_request():
            async with aclosing(
                runtime.events(
                    GenerationRequest(
                        model=runtime.model_id,
                        prompt="Write a long numbered list of 500 cities:",
                        max_tokens=512,
                    )
                )
            ) as events:
                async for event in events:
                    if event["type"] == "token":
                        started.set()

        task = asyncio.create_task(long_request())
        await started.wait()
        print(
            "long started",
            runtime.metrics()["active_requests"],
            backend.slot_stats(),
            flush=True,
        )
        short = await runtime.generate(
            GenerationRequest(model=runtime.model_id, prompt="2+2=", max_tokens=8)
        )
        print(
            "short completed while long active",
            not task.done(),
            short["text"],
            flush=True,
        )
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        print(
            "same worker", backend.process.pid == pid, backend.slot_stats(), flush=True
        )
        async with __import__("httpx").AsyncClient(
            base_url=backend.base_url, headers=backend.headers, trust_env=False
        ) as client:
            slots = (await client.get("/slots")).json()
            print(
                "native slots",
                [(s["id"], s["n_ctx"], s["is_processing"]) for s in slots],
                flush=True,
            )
        Path("artifacts/concurrency-probe.json").write_text(
            json.dumps(
                {
                    "pid_unchanged": backend.process.pid == pid,
                    "short_record": short["metadata"],
                    "slots": backend.slot_stats(),
                    "native_contexts": [s["n_ctx"] for s in slots],
                },
                indent=2,
            )
            + "\n"
        )
    finally:
        await backend.aclose()


asyncio.run(main())

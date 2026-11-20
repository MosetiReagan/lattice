"""Opt-in, real CPU verification of the explicit four-slot configuration."""

import asyncio
import os
from contextlib import aclosing
from pathlib import Path

import pytest

from lattice.backends import create_backend
from lattice.config import load_settings
from lattice.runtime import Runtime
from lattice.types import GenerationRequest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("LATTICE_INTEGRATION") != "1",
        reason="Real CPU integration is opt-in",
    ),
]


@pytest.mark.parametrize("slots", [3, 4])
async def test_four_slot_load_and_request_limits(tmp_path, slots):
    settings = load_settings(Path(__file__).resolve().parents[1] / "configs/local.json")
    settings.native_slots = slots
    settings.admission_policy = "priority_cost"
    settings.log_directory = str(tmp_path)
    model = settings.models[0]
    backend = create_backend(settings, model)
    runtime = Runtime(settings, model.id, backend)
    try:
        await backend.start()
        results = await asyncio.gather(
            *(
                runtime.generate(
                    GenerationRequest(
                        model=model.id,
                        prompt=f"Return only the number {i}:",
                        max_tokens=16,
                    )
                )
                for i in range(8)
            )
        )
        assert all(result["metadata"]["status"] == "completed" for result in results)
        assert all(result["metadata"]["completion_tokens"] <= 16 for result in results)
        assert all(result["metadata"]["native_slots"] == slots for result in results)
        assert backend.slot_stats()["free"] == slots
        assert runtime.metrics()["active_requests"] == 0
        assert backend.slot_stats()["quarantined"] == 0
    finally:
        await backend.aclose()


async def test_four_slot_cancellation_preserves_peers(tmp_path):
    settings = load_settings(Path(__file__).resolve().parents[1] / "configs/local.json")
    settings.native_slots = 4
    settings.log_directory = str(tmp_path)
    model = settings.models[0]
    backend = create_backend(settings, model)
    runtime = Runtime(settings, model.id, backend)
    first = asyncio.Event()

    async def cancellable():
        request = GenerationRequest(
            model=model.id,
            prompt="Write an extremely long numbered list of cities:",
            max_tokens=256,
        )
        async with aclosing(runtime.events(request)) as stream:
            async for event in stream:
                if event["type"] == "token":
                    first.set()

    task = None
    try:
        await backend.start()
        pid = backend.process.pid
        task = asyncio.create_task(cancellable())
        await asyncio.wait_for(first.wait(), 15)
        peers = [
            asyncio.create_task(
                runtime.generate(
                    GenerationRequest(
                        model=model.id,
                        prompt=f"The capital of France is Paris. Repeat Paris {i}:",
                        max_tokens=16,
                    )
                )
            )
            for i in range(3)
        ]
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        results = await asyncio.gather(*peers)
        assert all(result["metadata"]["status"] == "completed" for result in results)
        assert backend.process.pid == pid
        assert backend.slot_stats()["free"] == 4
        assert backend.slot_stats()["quarantined"] == 0
    finally:
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await backend.aclose()

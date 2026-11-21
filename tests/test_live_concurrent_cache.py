"""Real pinned CPU verification; no inference speed is asserted by tests."""

import asyncio
import os
from contextlib import aclosing
from pathlib import Path

import pytest

from lattice.backends import create_backend
from lattice.backends.batched import BatchedLlamaBackend
from lattice.config import load_settings
from lattice.runtime import Runtime
from lattice.types import GenerationRequest, Optimization

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("LATTICE_INTEGRATION") != "1", reason="Real CPU model required"
    ),
]


async def test_per_slot_cache_reuse_and_private_invalidation(tmp_path):
    settings = load_settings(Path(__file__).resolve().parents[1] / "configs/local.json")
    settings.native_slots = 2
    settings.concurrent_prefix_cache = True
    settings.cache_limit_mb = 64
    settings.cache_min_tokens = 1
    settings.log_directory = str(tmp_path)
    model = settings.models[0]
    backend = BatchedLlamaBackend(settings, model)
    runtime = Runtime(settings, model.id, backend)
    prompt = (
        "Reference only: " + "alpha beta gamma delta " * 60 + "\nReturn only READY:"
    )
    try:
        results = []
        for mode in (
            "cached",
            "cached",
            "cached",
            "standard",
            "cached",
            "cached",
            "cached",
            "cached",
        ):
            result = await runtime.generate(
                GenerationRequest(
                    model=model.id,
                    prompt=prompt,
                    max_tokens=4,
                    optimization=Optimization(mode=mode),
                )
            )
            assert result["metadata"]["strategy"] == mode
            assert result["metadata"]["backend"]["strategy"] == mode
            results.append(result)
        assert len({tuple(row["token_ids"]) for row in results}) == 1
        assert [row["metadata"]["native_slot"] for row in results] == [
            0,
            1,
            0,
            1,
            0,
            1,
            0,
            1,
        ]
        counts = [row["metadata"]["tokens_cached"] for row in results]
        assert counts[:2] == [0, 0]
        assert counts[2] > 100
        assert counts[3] == counts[5] == 0
        assert counts[4] > 100 and counts[6] > 100 and counts[7] > 100
        assert backend._strategy == "standard"  # no shared mode mutation
        assert backend.slot_stats()["free"] == 2
    finally:
        await backend.aclose()
    assert all(not prefix.tokens for prefix in backend._prefixes.values())


async def test_cached_peer_survives_standard_request_cancellation(tmp_path):
    settings = load_settings(Path(__file__).resolve().parents[1] / "configs/local.json")
    settings.native_slots = 2
    settings.concurrent_prefix_cache = True
    settings.cache_limit_mb = 64
    settings.cache_min_tokens = 1
    settings.log_directory = str(tmp_path)
    model = settings.models[0]
    backend = BatchedLlamaBackend(settings, model)
    runtime = Runtime(settings, model.id, backend)
    started = asyncio.Event()
    slot = None

    async def lengthy():
        nonlocal slot
        async with aclosing(
            runtime.events(
                GenerationRequest(
                    model=model.id,
                    prompt="Write a very long numbered list of cities:",
                    max_tokens=512,
                )
            )
        ) as events:
            async for event in events:
                if event["type"] == "token":
                    slot = next(s for s in backend._live if not s.completed).slot
                    started.set()

    task = asyncio.create_task(lengthy())
    try:
        await asyncio.wait_for(started.wait(), 10)
        peer = asyncio.create_task(
            runtime.generate(
                GenerationRequest(
                    model=model.id,
                    prompt="The capital of France is",
                    max_tokens=16,
                    optimization=Optimization(mode="cached"),
                )
            )
        )
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        result = await peer
        assert result["metadata"]["strategy"] == "cached"
        assert result["metadata"]["status"] == "completed"
        assert not backend._prefixes[slot].tokens
        assert backend._prefixes[result["metadata"]["native_slot"]].tokens
        assert backend.slot_stats()["verified_cancellations"] == 1
        assert backend.slot_stats()["free"] == 2
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await backend.aclose()


async def test_serial_cached_path_uses_product_configuration(tmp_path):
    settings = load_settings(Path(__file__).resolve().parents[1] / "configs/local.json")
    settings.native_slots = 1
    settings.native_ram_prompt_archive = False
    settings.cache_limit_mb = 64
    settings.cache_min_tokens = 1
    settings.log_directory = str(tmp_path)
    backend = create_backend(settings, settings.models[0])
    runtime = Runtime(settings, settings.models[0].id, backend)
    prompt = "Reference: " + "alpha beta gamma delta " * 60 + "\nReturn READY:"
    try:
        results = []
        for mode in ("standard", "cached", "cached", "standard", "cached"):
            result = await runtime.generate(
                GenerationRequest(
                    model=runtime.model_id,
                    prompt=prompt,
                    max_tokens=4,
                    optimization=Optimization(mode=mode),
                )
            )
            assert result["metadata"]["strategy"] == mode
            results.append(result)
        assert len({tuple(result["token_ids"]) for result in results}) == 1
        cached = [result["metadata"]["tokens_cached"] for result in results]
        assert cached[:2] == [0, 0] and cached[2] > 100
        assert cached[3:] == [0, 0]
    finally:
        backend.stop()

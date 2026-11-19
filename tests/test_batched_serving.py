"""Real CPU multi-slot and private native session-control verification."""

import asyncio
import os
from contextlib import aclosing
from pathlib import Path

import httpx
import pytest

from lattice.backends.batched import BatchedLlamaBackend
from lattice.config import load_settings
from lattice.runtime import Runtime
from lattice.types import GenerationRequest, LatticeError

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("LATTICE_INTEGRATION") != "1",
        reason="Real CPU model integration is opt-in",
    ),
]


@pytest.fixture
async def batched(tmp_path):
    settings = load_settings(Path(__file__).resolve().parents[1] / "configs/local.json")
    settings.native_slots = 2
    settings.log_directory = str(tmp_path)
    backend = BatchedLlamaBackend(settings, settings.models[0])
    runtime = Runtime(settings, settings.models[0].id, backend)
    await backend.start()
    try:
        yield runtime
    finally:
        await backend.aclose()


def request(runtime, **kwargs):
    return GenerationRequest(model=runtime.model_id, **kwargs)


async def test_short_request_finishes_while_long_request_is_still_generating(batched):
    runtime = batched
    backend = runtime.backend
    pid = backend.process.pid
    first = asyncio.Event()

    async def long():
        async with aclosing(
            runtime.events(
                request(
                    runtime,
                    prompt="Write a long numbered list of 500 cities:",
                    max_tokens=512,
                )
            )
        ) as stream:
            async for event in stream:
                if event["type"] == "token":
                    first.set()

    task = asyncio.create_task(long())
    try:
        await asyncio.wait_for(first.wait(), 10)
        result = await runtime.generate(
            request(runtime, prompt="The capital of France is", max_tokens=8)
        )
        assert result["metadata"]["status"] == "completed" and not task.done()
        assert result["metadata"]["native_slots"] == 2
        assert runtime.metrics()["active_requests"] == 1
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert backend.process.pid == pid
    assert backend.slot_stats()["verified_cancellations"] == 1
    assert backend.slot_stats()["free"] == 2
    async with httpx.AsyncClient(
        base_url=backend.base_url, headers=backend.headers, trust_env=False
    ) as client:
        slots = (await client.get("/slots")).json()
    assert [s["n_ctx"] for s in slots] == [runtime.settings.context_tokens] * 2
    assert not any(s["is_processing"] for s in slots)


async def test_cancelling_one_stream_does_not_cancel_the_other(batched):
    runtime = batched
    backend = runtime.backend
    pid = backend.process.pid
    events = [asyncio.Event(), asyncio.Event()]

    async def run(index):
        tokens = []
        async with aclosing(
            runtime.events(
                request(
                    runtime,
                    prompt=f"Write a long numbered list of cities, starting at {index + 1}:",
                    max_tokens=128,
                )
            )
        ) as stream:
            async for event in stream:
                if event["type"] == "token":
                    events[index].set()
                    tokens.extend(event["token_ids"])
                elif event["type"] == "done":
                    return tokens, event["record"]

    one = asyncio.create_task(run(0))
    two = asyncio.create_task(run(1))
    try:
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in events)), 10)
        assert runtime.metrics()["active_requests"] == 2
        one.cancel()
        with pytest.raises(asyncio.CancelledError):
            await one
        tokens, record = await two
        assert (
            tokens
            and record["status"] == "completed"
            and record["completion_tokens"] <= 128
        )
        assert backend.process.pid == pid
        assert backend.slot_stats()["unconfirmed_cleanup"] == 0
        assert backend.slot_stats()["free"] == 2
    finally:
        for task in (one, two):
            if not task.done():
                task.cancel()
        await asyncio.gather(one, two, return_exceptions=True)


async def test_timeout_during_prefill_does_not_interrupt_peer(batched):
    runtime = batched
    backend = runtime.backend
    pid = backend.process.pid
    first = asyncio.Event()

    async def peer():
        async with aclosing(
            runtime.events(
                request(
                    runtime,
                    prompt="Write a long numbered list of cities:",
                    max_tokens=128,
                )
            )
        ) as stream:
            async for event in stream:
                if event["type"] == "token":
                    first.set()
                if event["type"] == "done":
                    return event["record"]

    task = asyncio.create_task(peer())
    try:
        await asyncio.wait_for(first.wait(), 10)
        with pytest.raises(LatticeError) as error:
            await runtime.generate(
                request(
                    runtime,
                    prompt="The report records observations. " * 250,
                    max_tokens=32,
                    timeout_seconds=0.1,
                )
            )
        assert error.value.code == "request_timeout"
        record = await task
        assert record["status"] == "completed" and backend.process.pid == pid
        for _ in range(100):
            if backend.slot_stats()["free"] == 2:
                break
            await asyncio.sleep(0.02)
        assert backend.slot_stats()["free"] == 2
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_shared_worker_constraints_do_not_restart_peer(batched):
    runtime = batched
    pid = runtime.backend.process.pid
    with pytest.raises(LatticeError) as error:
        await runtime.generate(
            request(runtime, prompt="Hello", max_tokens=4, max_memory_mb=1024)
        )
    assert error.value.code == "budget_infeasible"
    with pytest.raises(LatticeError) as error:
        await runtime.generate(
            request(
                runtime,
                prompt="Hello",
                max_tokens=4,
                optimization={"mode": "cached", "allow_fallback": False},
            )
        )
    assert error.value.code == "concurrent_strategy_unqualified"
    result = await runtime.generate(
        request(
            runtime, prompt="Hello", max_tokens=4, optimization={"mode": "adaptive"}
        )
    )
    assert (
        result["metadata"]["strategy"] == "standard"
        and result["metadata"]["fallback_reason"]
    )
    assert runtime.backend.process.pid == pid

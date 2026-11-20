"""Mocked burst-grace semantics and cancellation; not hardware evidence."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from lattice.config import Settings
from lattice.runtime import Runtime
from lattice.types import GenerationRequest, LatticeError


class ReadyBackend:
    native_slots = 4

    def __init__(self):
        self.identity = {"name": "mock"}
        self.received = []

    async def events(self, request):
        self.received.append(request)
        yield {"type": "prefill", "prompt_tokens": 1}
        yield {"type": "token", "text": "same", "token_ids": [1]}
        yield {
            "type": "backend_done",
            "completion_tokens": 1,
            "finish_reason": "stop",
            "backend_timings": {},
        }


def create(settings):
    settings.native_slots = 4
    settings.admission_policy = "priority_cost_coalesce"
    backend = ReadyBackend()
    return Runtime(settings, "test-model", backend), backend


async def test_only_default_priority_bulk_gets_bounded_grace(settings):
    runtime, backend = create(settings)
    sleep = AsyncMock()
    with patch("lattice.runtime.asyncio.sleep", sleep):
        for prompt, cap, priority in [
            ("x" * 2000, 16, 0),
            ("small", 8, 0),
            ("x" * 2000, 16, 3),
            ("small", 64, 0),
        ]:
            request = GenerationRequest(
                model="test-model",
                prompt=prompt,
                max_tokens=cap,
                priority=priority,
                temperature=0.7,
                seed=81,
            )
            await runtime.generate(request)
            assert backend.received[-1] is request
    assert sleep.await_count == 2
    assert all(call.args == (0.05,) for call in sleep.await_args_list)


async def test_grace_cancellation_never_leaks_admission(settings):
    runtime, backend = create(settings)
    task = asyncio.create_task(
        runtime.generate(
            GenerationRequest(model="test-model", prompt="x" * 2000, max_tokens=16)
        )
    )
    await asyncio.sleep(0.005)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not backend.received
    assert runtime.waiting == runtime.lock.active == 0
    assert runtime.metrics()["counters"]["cancelled"] == 1


@pytest.mark.parametrize("max_queue", [0, 1])
async def test_grace_waiters_are_bounded_before_slots_are_occupied(settings, max_queue):
    settings.max_queue = max_queue
    runtime, backend = create(settings)
    entered = asyncio.Queue()
    release = asyncio.Event()

    async def grace(_delay):
        entered.put_nowait(True)
        await release.wait()

    def request():
        return GenerationRequest(model="test-model", prompt="x" * 2000, max_tokens=16)

    tasks = []
    with patch("lattice.runtime.asyncio.sleep", grace):
        try:
            for _ in range(4 + max_queue):
                tasks.append(asyncio.create_task(runtime.generate(request())))
                await entered.get()
            assert runtime.waiting == 4 + max_queue
            assert runtime.lock.active == 0
            with pytest.raises(LatticeError) as exc:
                await runtime.generate(request())
            assert exc.value.code == "queue_full"
            assert not backend.received
            # A cancelled grace waiter frees capacity immediately.
            cancelled = tasks.pop()
            cancelled.cancel()
            with pytest.raises(asyncio.CancelledError):
                await cancelled
            tasks.append(asyncio.create_task(runtime.generate(request())))
            await entered.get()
            release.set()
            await asyncio.gather(*tasks)
            assert runtime.waiting == runtime.lock.active == 0
            assert len(backend.received) == 4 + max_queue
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


def test_policy_is_configurable_and_default_unchanged(settings):
    values = settings.model_dump()
    values["admission_policy"] = "priority_cost_coalesce"
    assert Settings.model_validate(values).admission_policy == "priority_cost_coalesce"
    values.pop("admission_policy")
    assert Settings.model_validate(values).admission_policy == "priority_fifo"


def test_invalid_native_batch_configuration_rejected(settings):
    values = settings.model_dump()
    values.update(batch_tokens=64, ubatch_tokens=128)
    with pytest.raises(ValueError, match="cannot exceed"):
        Settings.model_validate(values)

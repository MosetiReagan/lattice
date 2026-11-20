"""Mocked admission invariants; not evidence of native execution performance."""

import asyncio

import pytest

from lattice.runtime import Runtime
from lattice.types import GenerationRequest


class HeldBackend:
    native_slots = 4

    def __init__(self):
        self.identity = {"name": "mock"}
        self.started = {}
        self.release = {}

    async def events(self, request):
        key = request.prompt[:12]
        event = self.release.setdefault(key, asyncio.Event())
        self.started[key] = True
        yield {"type": "prefill", "prompt_tokens": 4}
        await event.wait()
        yield {"type": "token", "text": "ok", "token_ids": [1]}
        yield {
            "type": "backend_done",
            "completion_tokens": 1,
            "finish_reason": "stop",
            "backend_timings": {},
        }


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0.001)


def setup(settings):
    settings.native_slots = 4
    settings.max_queue = 32
    settings.admission_policy = "priority_cost_reserve"
    backend = HeldBackend()
    return Runtime(settings, "test-model", backend), backend


def request(index, bulk=True, priority=0):
    name = f"request-{index:03d}:"
    return GenerationRequest(
        model="test-model",
        prompt=name + ("x" * 2000 if bulk else "small"),
        max_tokens=16,
        priority=priority,
    )


async def test_reservation_admits_small_without_releasing_active_bulk(settings):
    runtime, backend = setup(settings)
    tasks = [asyncio.create_task(runtime.generate(request(i))) for i in range(4)]
    try:
        await until(lambda: len(backend.started) == 3)
        small = asyncio.create_task(runtime.generate(request(9, bulk=False)))
        tasks.append(small)
        await until(lambda: "request-009:" in backend.started)
        assert len(backend.started) == 4
        assert "request-003:" not in backend.started
        backend.release["request-009:"].set()
        await small
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    assert runtime._small_pending == 0
    assert runtime._small_drained.is_set()
    assert runtime.lock.active == runtime.bulk_lock.active == 0


async def test_cancelled_small_and_queued_bulk_release_every_permit(settings):
    runtime, backend = setup(settings)
    tasks = [asyncio.create_task(runtime.generate(request(i))) for i in range(6)]
    try:
        await until(lambda: len(backend.started) == 3)
        small = asyncio.create_task(runtime.generate(request(9, bulk=False)))
        tasks.append(small)
        await until(lambda: runtime._small_pending == 1)
        # Free one bulk lane while a small request is active, exercising drain wait.
        backend.release["request-000:"].set()
        await tasks[0]
        await asyncio.sleep(0.01)
        assert "request-003:" not in backend.started
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    assert runtime._small_pending == 0
    assert runtime._small_drained.is_set()
    assert runtime.waiting == 0
    assert runtime.lock.active == runtime.bulk_lock.active == 0


async def test_explicit_high_priority_bulk_can_use_reserved_lane(settings):
    runtime, backend = setup(settings)
    tasks = [asyncio.create_task(runtime.generate(request(i))) for i in range(3)]
    try:
        await until(lambda: len(backend.started) == 3)
        high = asyncio.create_task(runtime.generate(request(9, priority=3)))
        tasks.append(high)
        await until(lambda: "request-009:" in backend.started)
        assert runtime.lock.active == 4
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    assert runtime.lock.active == runtime.bulk_lock.active == 0


def test_single_slot_reservation_rejected(settings):
    settings.admission_policy = "priority_cost_reserve"
    with pytest.raises(ValueError, match="at least two"):
        Runtime(settings, "test-model", HeldBackend())

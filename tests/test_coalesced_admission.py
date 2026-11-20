"""Mocked burst-grace semantics and cancellation; not hardware evidence."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from lattice.config import Settings
from lattice.runtime import Runtime
from lattice.types import GenerationRequest


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

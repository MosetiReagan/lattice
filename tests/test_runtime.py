import asyncio
import json
from contextlib import aclosing

import pytest

from lattice.runtime import Runtime
from lattice.types import GenerationRequest, LatticeError


class FakeBackend:
    """Mocked control-plane tests, never evidence of hardware support."""

    def __init__(self, blocked=False):
        self.identity = {"name": "fake", "device": "mock"}
        self.blocked = blocked
        self.started = asyncio.Event()
        self.closed = 0
        self.fail = False

    async def start(self):
        pass

    def stop(self):
        pass

    async def events(self, request):
        try:
            yield {"type": "prefill", "prompt_tokens": 2}
            self.started.set()
            if self.blocked:
                await asyncio.Event().wait()
            if self.fail:
                raise LatticeError("Injected failure", 502, "injected")
            yield {"type": "token", "text": "hello", "token_ids": [42]}
            yield {
                "type": "backend_done",
                "completion_tokens": 1,
                "finish_reason": "stop",
                "backend_timings": {"prompt_ms": 1},
                "tokens_cached": 0,
            }
        finally:
            self.closed += 1


def request(**kwargs):
    return GenerationRequest(model="test-model", prompt="private-input", **kwargs)


async def test_metrics_do_not_log_content(settings):
    backend = FakeBackend()
    runtime = Runtime(settings, "test-model", backend)
    result = await runtime.generate(request())
    assert result["text"] == "hello"
    record = json.loads(
        (
            __import__("pathlib").Path(settings.log_directory) / "requests.jsonl"
        ).read_text()
    )
    assert record["status"] == "completed" and record["completion_tokens"] == 1
    assert "private-input" not in json.dumps(record)
    assert "hello" not in json.dumps(record)
    assert not runtime.lock.locked() and runtime.waiting == 0


async def test_queue_timeout_and_cancellation_release(settings):
    backend = FakeBackend(blocked=True)
    runtime = Runtime(settings, "test-model", backend)
    active = asyncio.create_task(runtime.generate(request()))
    await backend.started.wait()
    queued = asyncio.create_task(runtime.generate(request(timeout_seconds=0.1)))
    await asyncio.sleep(0)
    with pytest.raises(LatticeError) as exc:
        await runtime.generate(request())
    assert exc.value.code == "queue_full"
    with pytest.raises(LatticeError) as exc:
        await queued
    assert exc.value.code == "request_timeout"
    active.cancel()
    with pytest.raises(asyncio.CancelledError):
        await active
    assert runtime.waiting == 0 and not runtime.lock.locked()
    assert backend.closed == 1
    backend.blocked = False
    assert (await runtime.generate(request()))["text"] == "hello"


async def test_close_stream_at_start(settings):
    backend = FakeBackend()
    runtime = Runtime(settings, "test-model", backend)
    async with aclosing(runtime.events(request())) as events:
        assert (await anext(events))["type"] == "start"
    assert not runtime.lock.locked() and backend.closed == 1
    assert runtime.metrics()["counters"]["cancelled"] == 1


async def test_error_isolation_and_model_identity(settings):
    backend = FakeBackend()
    runtime = Runtime(settings, "test-model", backend)
    with pytest.raises(LatticeError):
        await runtime.generate(GenerationRequest(model="../bad", prompt="test"))
    backend.fail = True
    with pytest.raises(LatticeError):
        await runtime.generate(request())
    backend.fail = False
    assert (await runtime.generate(request()))["text"] == "hello"
    assert not runtime.lock.locked()

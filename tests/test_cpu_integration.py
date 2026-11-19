"""Opt-in real-model CPU integration. No mocked GPU claims."""

import os
from contextlib import aclosing
from pathlib import Path

import pytest

from lattice.backends.llama_cpp import LlamaCppBackend
from lattice.config import load_settings
from lattice.runtime import Runtime
from lattice.types import GenerationRequest, LatticeError

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("LATTICE_INTEGRATION") != "1",
        reason="Set LATTICE_INTEGRATION=1 for real model tests",
    ),
]


@pytest.fixture
async def real_runtime(tmp_path):
    settings = load_settings(Path(__file__).resolve().parents[1] / "configs/local.json")
    settings.log_directory = str(tmp_path)
    entry = settings.models[0]
    backend = LlamaCppBackend(settings, entry)
    runtime = Runtime(settings, entry.id, backend)
    await backend.start()
    try:
        yield runtime
    finally:
        backend.stop()


def req(runtime, **kwargs):
    return GenerationRequest(model=runtime.model_id, **kwargs)


async def test_real_generation_stream_and_determinism(real_runtime):
    runtime = real_runtime
    request = req(runtime, prompt="The capital of France is", max_tokens=16)
    standard = await runtime.generate(request)
    assert "Paris" in standard["text"] and len(standard["token_ids"]) <= 16
    assert standard["metadata"]["backend_timings"]["prompt_n"] > 0
    tokens, text, done = [], [], None
    async with aclosing(runtime.events(request)) as stream:
        async for event in stream:
            if event["type"] == "token":
                tokens.extend(event["token_ids"])
                text.append(event["text"])
            elif event["type"] == "done":
                done = event["record"]
    assert tokens == standard["token_ids"]
    assert "".join(text) == standard["text"]
    assert done["status"] == "completed"
    assert done["backend_timings"]["cache_n"] == 0


async def test_real_chat_and_context_rejection(real_runtime):
    runtime = real_runtime
    result = await runtime.generate(
        req(
            runtime,
            messages=[{"role": "user", "content": "What is 2 + 2? Answer briefly."}],
            max_tokens=32,
        )
    )
    assert result["text"].strip()
    with pytest.raises(LatticeError) as error:
        await runtime.generate(req(runtime, prompt="word " * 3000, max_tokens=32))
    assert error.value.code == "context_limit"
    assert runtime.backend.process is not None
    assert not runtime.lock.locked()


async def test_real_cancellation_stops_worker_and_recovers(real_runtime):
    runtime = real_runtime
    old_process = runtime.backend.process
    async with aclosing(
        runtime.events(req(runtime, prompt="Count from one onwards:", max_tokens=512))
    ) as stream:
        async for event in stream:
            if event["type"] == "token":
                break
    assert old_process.poll() is not None
    assert runtime.backend.process is None
    assert not runtime.lock.locked()
    recovered = await runtime.generate(req(runtime, prompt="Hello", max_tokens=4))
    assert recovered["metadata"]["status"] == "completed"
    assert runtime.backend.process.pid != old_process.pid


async def test_real_timeout_isolation(real_runtime):
    runtime = real_runtime
    with pytest.raises(LatticeError) as error:
        await runtime.generate(
            req(
                runtime,
                prompt="List all integers:",
                max_tokens=512,
                timeout_seconds=0.1,
            )
        )
    assert error.value.code == "request_timeout"
    assert not runtime.lock.locked()
    assert runtime.backend.process is None
    assert (await runtime.generate(req(runtime, prompt="Hello", max_tokens=2)))[
        "metadata"
    ]["status"] == "completed"


async def test_real_artifact_tampering_rejected(real_runtime):
    runtime = real_runtime
    runtime.backend.stop()
    runtime.backend.settings.backend_sha256 = "0" * 64
    with pytest.raises(LatticeError) as error:
        await runtime.generate(req(runtime, prompt="Hello", max_tokens=2))
    assert error.value.code == "artifact_mismatch"
    assert runtime.backend.process is None

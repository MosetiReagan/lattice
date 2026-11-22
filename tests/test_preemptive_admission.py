"""Tests for preemptive priority admission, active slot signaling, and automatic resumption."""

import asyncio

from lattice.config import Settings
from lattice.runtime import Runtime
from lattice.scheduler.fair import FairSemaphore
from lattice.types import GenerationRequest


async def test_preemptive_semaphore_signaling():
    sem = FairSemaphore(capacity=1, preemptive=True)
    p1 = await sem.acquire(priority=0)
    assert not p1.is_preempted

    order = []

    async def high_priority_requester():
        p2 = await sem.acquire(priority=2)
        order.append("high")
        assert not p2.is_preempted
        sem.release(p2)

    task = asyncio.create_task(high_priority_requester())
    await asyncio.sleep(0.01)

    # High priority request arrival should have signaled preemption on p1
    assert p1.is_preempted

    # Low priority yields
    order.append("low_preempted")
    sem.release(p1)

    await task
    assert order == ["low_preempted", "high"]
    assert not sem.locked()


async def test_preemptive_semaphore_targets_lowest_priority_holder():
    sem = FairSemaphore(capacity=2, preemptive=True)
    p_low = await sem.acquire(priority=0)
    p_med = await sem.acquire(priority=1)

    assert not p_low.is_preempted
    assert not p_med.is_preempted

    async def high_requester():
        p_high = await sem.acquire(priority=3)
        sem.release(p_high)

    task = asyncio.create_task(high_requester())
    await asyncio.sleep(0.01)

    # Only the lowest priority holder should be targeted
    assert p_low.is_preempted
    assert not p_med.is_preempted

    sem.release(p_low)
    await task
    sem.release(p_med)
    assert not sem.locked()


class StreamingPreemptibleBackend:
    """Mock backend that streams tokens step-by-step and tracks cancellation."""

    def __init__(self):
        self.identity = {"name": "mock-streamer"}
        self.started = asyncio.Event()
        self.calls = []

    async def start(self):
        pass

    def stop(self):
        pass

    async def events(self, request):
        self.calls.append(request.model_copy(deep=True))
        yield {"type": "prefill", "prompt_tokens": len(request.prompt.split())}
        self.started.set()

        tokens_to_emit = request.max_tokens
        for i in range(tokens_to_emit):
            await asyncio.sleep(0.02)
            yield {
                "type": "token",
                "text": f" token_{i}",
                "token_ids": [100 + i],
            }

        yield {
            "type": "backend_done",
            "completion_tokens": tokens_to_emit,
            "finish_reason": "stop",
            "backend_timings": {"prompt_ms": 1, "eval_ms": 10},
            "tokens_cached": 0,
        }


async def test_runtime_preemption_and_automatic_resume(settings: Settings):
    settings.native_slots = 1
    settings.admission_policy = "priority_preemptive"
    settings.preemption_auto_resume = True

    backend = StreamingPreemptibleBackend()
    runtime = Runtime(settings, "test-model", backend)

    low_req = GenerationRequest(
        model="test-model",
        prompt="Background batch task:",
        max_tokens=6,
        priority=0,
    )
    high_req = GenerationRequest(
        model="test-model",
        prompt="Interactive query:",
        max_tokens=2,
        priority=3,
    )

    low_events = []
    high_events = []

    async def run_low():
        async for ev in runtime.events(low_req):
            low_events.append(ev)

    async def run_high():
        async for ev in runtime.events(high_req):
            high_events.append(ev)

    task_low = asyncio.create_task(run_low())
    await backend.started.wait()
    # Allow a couple of tokens to be emitted by the low-priority job
    await asyncio.sleep(0.05)

    # Launch the high-priority request while low-priority is running
    task_high = asyncio.create_task(run_high())

    # Wait for both to finish
    await asyncio.gather(task_low, task_high)

    # Verify high priority request completed promptly
    high_tokens = [e["text"] for e in high_events if e["type"] == "token"]
    assert len(high_tokens) == 2

    # Verify low priority was preempted, resumed, and completed all requested tokens
    low_tokens = [e["text"] for e in low_events if e["type"] == "token"]
    assert len(low_tokens) == 6

    # Verify counters
    assert runtime.counters["requests_preempted"] >= 1
    assert runtime.counters["requests_resumed"] >= 1
    assert not runtime.lock.locked()


async def test_runtime_preemption_without_auto_resume(settings: Settings):
    settings.native_slots = 1
    settings.admission_policy = "priority_preemptive"
    settings.preemption_auto_resume = False

    backend = StreamingPreemptibleBackend()
    runtime = Runtime(settings, "test-model", backend)

    low_req = GenerationRequest(
        model="test-model",
        prompt="Background batch task:",
        max_tokens=6,
        priority=0,
    )
    high_req = GenerationRequest(
        model="test-model",
        prompt="Interactive query:",
        max_tokens=2,
        priority=3,
    )

    low_events = []
    high_events = []

    async def run_low():
        async for ev in runtime.events(low_req):
            low_events.append(ev)

    async def run_high():
        async for ev in runtime.events(high_req):
            high_events.append(ev)

    task_low = asyncio.create_task(run_low())
    await backend.started.wait()
    await asyncio.sleep(0.05)

    task_high = asyncio.create_task(run_high())
    await asyncio.gather(task_low, task_high)

    done_event = next(e for e in low_events if e["type"] == "backend_done")
    assert done_event["finish_reason"] == "preempted"
    assert runtime.counters["requests_preempted"] >= 1
    assert runtime.counters["requests_resumed"] == 0


def test_cli_parser_accepts_priority_preemptive():
    from lattice.cli import parser

    args = parser().parse_args(
        [
            "serve",
            "--model",
            "qwen2.5-0.5b-instruct-f16",
            "--admission-policy",
            "priority_preemptive",
        ]
    )
    assert args.command == "serve"
    assert args.model == "qwen2.5-0.5b-instruct-f16"
    assert args.admission_policy == "priority_preemptive"

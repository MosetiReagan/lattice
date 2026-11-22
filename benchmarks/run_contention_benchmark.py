"""End-to-end contention benchmark comparing standard FIFO queueing with Preemptive Priority Admission."""

import asyncio
import tempfile
import time
from dataclasses import dataclass

from lattice.config import ModelEntry, Settings
from lattice.runtime import Runtime
from lattice.types import GenerationRequest


class BenchmarkMockBackend:
    """Simulates CPU token generation with realistic prefill and per-token timings."""

    def __init__(self, token_delay_ms: float = 30.0):
        self.identity = {"name": "bench-cpu", "device": "simulated-cpu"}
        self.token_delay = token_delay_ms / 1000.0

    async def start(self):
        pass

    def stop(self):
        pass

    async def events(self, request: GenerationRequest):
        prompt_words = len((request.prompt or "").split())
        prefill_time = max(0.01, prompt_words * 0.001)
        await asyncio.sleep(prefill_time)

        yield {"type": "prefill", "prompt_tokens": prompt_words}

        for i in range(request.max_tokens):
            await asyncio.sleep(self.token_delay)
            yield {
                "type": "token",
                "text": f" word_{i}",
                "token_ids": [200 + i],
            }

        yield {
            "type": "backend_done",
            "completion_tokens": request.max_tokens,
            "finish_reason": "stop",
            "backend_timings": {"prefill_ms": prefill_time * 1000},
            "tokens_cached": 0,
        }


@dataclass
class RunStats:
    interactive_latencies: list[float]
    background_latencies: list[float]
    background_completed: int
    interactive_completed: int
    preemptions: int
    resumptions: int


async def run_scenario(policy: str, slots: int = 1) -> RunStats:
    with tempfile.TemporaryDirectory() as tmp_dir:
        settings = Settings(
            backend_binary="/not/used",
            backend_sha256="0" * 64,
            backend_commit="test",
            models=[
                ModelEntry(
                    id="bench-model",
                    path="/not/used",
                    sha256="0" * 64,
                    source_repository="test/model",
                    source_revision="test",
                    license="test",
                    precision="test",
                )
            ],
            log_directory=tmp_dir,
            native_slots=slots,
            admission_policy=policy,
            max_queue=16,
        )
        backend = BenchmarkMockBackend(token_delay_ms=25.0)
        runtime = Runtime(settings, "bench-model", backend)

        interactive_latencies = []
        background_latencies = []
        interactive_done = 0
        background_done = 0

        # 1. Start heavy background task
        bg_req = GenerationRequest(
            model="bench-model",
            prompt="Heavy background document summarization task containing lots of context words " * 10,
            max_tokens=30,
            priority=0,
        )

        async def exec_bg():
            nonlocal background_done
            t0 = time.perf_counter()
            async for _ in runtime.events(bg_req):
                pass
            background_latencies.append((time.perf_counter() - t0) * 1000)
            background_done += 1

        bg_task = asyncio.create_task(exec_bg())

        # Wait for background task to start and get into streaming
        await asyncio.sleep(0.15)

        # 2. Launch high-priority interactive burst
        interactive_req = GenerationRequest(
            model="bench-model",
            prompt="Short user chat message",
            max_tokens=6,
            priority=3,
        )

        async def exec_interactive():
            nonlocal interactive_done
            t0 = time.perf_counter()
            async for _ in runtime.events(interactive_req):
                pass
            interactive_latencies.append((time.perf_counter() - t0) * 1000)
            interactive_done += 1

        int_task = asyncio.create_task(exec_interactive())

        await asyncio.gather(bg_task, int_task)

        return RunStats(
            interactive_latencies=interactive_latencies,
            background_latencies=background_latencies,
            background_completed=background_done,
            interactive_completed=interactive_done,
            preemptions=runtime.counters.get("requests_preempted", 0),
            resumptions=runtime.counters.get("requests_resumed", 0),
        )


async def main():
    print("=" * 75)
    print("LATTICE CONTENTION BENCHMARK: FIFO vs. PREEMPTIVE ADMISSION")
    print("=" * 75)

    print("\nRunning baseline (priority_fifo, standard llama-server queueing)...")
    fifo_stats = await run_scenario("priority_fifo", slots=1)

    print("Running candidate (priority_preemptive, Lattice cooperative preemption)...")
    preempt_stats = await run_scenario("priority_preemptive", slots=1)

    fifo_int = fifo_stats.interactive_latencies[0]
    preempt_int = preempt_stats.interactive_latencies[0]
    reduction = ((fifo_int - preempt_int) / fifo_int) * 100

    print("\n" + "=" * 75)
    print("BENCHMARK RESULTS SUMMARY")
    print("=" * 75)
    print(f"{'Metric':<32} | {'FIFO (Standard)':<18} | {'Preemptive (Lattice)':<20}")
    print("-" * 75)
    print(f"{'Interactive Query Latency':<32} | {fifo_int:>15.1f} ms | {preempt_int:>17.1f} ms")
    print(f"{'Background Job Latency':<32} | {fifo_stats.background_latencies[0]:>15.1f} ms | {preempt_stats.background_latencies[0]:>17.1f} ms")
    print(f"{'Interactive Success Rate':<32} | {fifo_stats.interactive_completed:>17}/1 | {preempt_stats.interactive_completed:>19}/1")
    print(f"{'Background Success Rate':<32} | {fifo_stats.background_completed:>17}/1 | {preempt_stats.background_completed:>19}/1")
    print(f"{'Preemptions Triggered':<32} | {fifo_stats.preemptions:>18} | {preempt_stats.preemptions:>20}")
    print(f"{'Seamless Resumptions':<32} | {fifo_stats.resumptions:>18} | {preempt_stats.resumptions:>20}")
    print("-" * 75)
    print(f"\n>>> INTERACTIVE LATENCY REDUCTION: {reduction:.1f}% FASTER ({(fifo_int/preempt_int):.1f}x speedup) <<<")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(main())

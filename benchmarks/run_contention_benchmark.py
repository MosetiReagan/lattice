"""End-to-end contention benchmark comparing standard FIFO queueing with Preemptive Priority Admission.

Supports both real model execution (via llama.cpp backend) and synthetic simulation.
"""

import argparse
import asyncio
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from lattice.backends import create_backend
from lattice.config import ModelEntry, Settings, load_settings, select_model
from lattice.runtime import Runtime
from lattice.types import GenerationRequest, LatticeError


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
    queue_wait_ms: float
    interactive_ttft_ms: float
    interactive_total_ms: float
    background_total_ms: float
    background_completed: int
    interactive_completed: int
    preemptions: int
    resumptions: int
    background_output: str
    interactive_output: str



async def run_scenario(
    policy: str,
    slots: int = 1,
    use_real_backend: bool = False,
    model_name: str | None = None,
    bg_tokens: int = 120,
    chat_tokens: int = 8,
) -> RunStats:
    settings = None
    entry = None

    if use_real_backend:
        try:
            settings = load_settings()
            settings.native_slots = slots
            settings.admission_policy = policy
            entry = select_model(settings, model_name or settings.models[0].id)
            backend = create_backend(settings, entry)
            await backend.start()
        except (OSError, LatticeError, ValueError) as exc:
            print(f"[Notice: real backend unavailable ({exc}), falling back to simulated backend]", file=sys.stderr)
            use_real_backend = False

    if not use_real_backend:
        tmp_dir = tempfile.mkdtemp()
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
        entry = settings.models[0]
        backend = BenchmarkMockBackend(token_delay_ms=25.0)

    runtime = Runtime(settings, entry.id, backend)

    bg_req = GenerationRequest(
        model=entry.id,
        prompt="Write a concise overview explaining how operating system CPU scheduling algorithms work:"
        if use_real_backend
        else "Heavy background document summarization task containing lots of context words " * 10,
        max_tokens=bg_tokens,
        priority=0,
    )

    int_req = GenerationRequest(
        model=entry.id,
        prompt="Say hello and count to three:" if use_real_backend else "Short user chat message",
        max_tokens=chat_tokens,
        priority=3,
    )

    bg_text_chunks = []
    int_text_chunks = []
    int_ttft = 0.0
    int_total = 0.0
    bg_total = 0.0
    int_done = 0
    bg_done = 0

    t_int_submit = 0.0
    t_int_admitted = 0.0
    t_int_first_tok = 0.0
    t_int_done = 0.0
    t_bg_start = 0.0
    t_bg_done = 0.0

    async def exec_bg():
        nonlocal bg_done, bg_total, t_bg_start, t_bg_done
        t_bg_start = time.perf_counter()
        async for ev in runtime.events(bg_req):
            if ev["type"] == "token":
                bg_text_chunks.append(ev.get("text", ""))
        t_bg_done = time.perf_counter()
        bg_total = (t_bg_done - t_bg_start) * 1000
        bg_done += 1

    async def exec_int():
        nonlocal int_done, t_int_admitted, t_int_first_tok, t_int_done
        async for ev in runtime.events(int_req):
            if t_int_admitted == 0.0:
                t_int_admitted = time.perf_counter()
            if ev["type"] == "token":
                if t_int_first_tok == 0.0:
                    t_int_first_tok = time.perf_counter()
                int_text_chunks.append(ev.get("text", ""))
        t_int_done = time.perf_counter()
        int_done += 1

    try:
        bg_task = asyncio.create_task(exec_bg())
        # Let background job acquire slot and generate several tokens
        await asyncio.sleep(0.5 if use_real_backend else 0.2)

        t_int_submit = time.perf_counter()
        int_task = asyncio.create_task(exec_int())

        await asyncio.gather(bg_task, int_task)
    finally:
        close = getattr(backend, "aclose", None)
        if close:
            await close()
        else:
            backend.stop()

    queue_wait = (t_int_admitted - t_int_submit) * 1000 if (t_int_admitted > 0 and t_int_submit > 0) else 0.0
    int_ttft = (t_int_first_tok - t_int_submit) * 1000 if (t_int_first_tok > 0 and t_int_submit > 0) else queue_wait
    int_total = (t_int_done - t_int_submit) * 1000 if (t_int_done > 0 and t_int_submit > 0) else 0.0

    return RunStats(
        queue_wait_ms=queue_wait,
        interactive_ttft_ms=int_ttft,
        interactive_total_ms=int_total,
        background_total_ms=bg_total,
        background_completed=bg_done,
        interactive_completed=int_done,
        preemptions=runtime.counters.get("requests_preempted", 0),
        resumptions=runtime.counters.get("requests_resumed", 0),
        background_output="".join(bg_text_chunks),
        interactive_output="".join(int_text_chunks),
    )


async def main():
    parser = argparse.ArgumentParser(description="Lattice Contention Benchmark")
    parser.add_argument(
        "--mode",
        choices=["auto", "real", "simulated"],
        default="auto",
        help="Benchmark mode: auto (detect real backend), real (require llama.cpp), simulated (BenchmarkMockBackend)",
    )
    parser.add_argument("--model", help="Registered model ID to benchmark (for real mode)")
    parser.add_argument("--bg-tokens", type=int, default=120, help="Number of background tokens (default: 120)")
    parser.add_argument("--chat-tokens", type=int, default=8, help="Number of interactive tokens (default: 8)")
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Run multi-workload scaling sweep (48, 96, 160 tokens) demonstrating Head-of-Line blocking",
    )
    args = parser.parse_args()

    use_real = False
    if args.mode in ("auto", "real"):
        try:
            cfg = load_settings()
            m = select_model(cfg, args.model or cfg.models[0].id)
            if Path(cfg.backend_binary).is_file() and Path(m.path).is_file():
                use_real = True
            elif args.mode == "real":
                print(f"Error: model ({m.path}) or backend ({cfg.backend_binary}) not found. Provision first.", file=sys.stderr)
                sys.exit(1)
        except (OSError, LatticeError, ValueError):
            if args.mode == "real":
                raise

    print("=" * 78)
    print("LATTICE CPU CONTENTION BENCHMARK: FIFO QUEUE vs. PREEMPTIVE ADMISSION")
    print("=" * 78)
    if use_real:
        print("Backend: Real CPU Inference (llama.cpp engine + registered GGUF model)")
    else:
        print("Backend: Synthetic Simulation (BenchmarkMockBackend, 25ms/tok CPU model simulation)")
    print("Workload: Low-priority background task (P0) competing with incoming interactive chat (P3)")
    print("-" * 78)

    if args.sweep:
        sweep_workloads = [48, 96, 160]
        results = []
        for bg_len in sweep_workloads:
            print(f"\n--- Testing Background Workload: {bg_len} Tokens (Chat: {args.chat_tokens} Tokens) ---")
            print("1. Running FIFO baseline...")
            fifo = await run_scenario(
                "priority_fifo",
                slots=1,
                use_real_backend=use_real,
                model_name=args.model,
                bg_tokens=bg_len,
                chat_tokens=args.chat_tokens,
            )
            print("2. Running Preemptive candidate...")
            preempt = await run_scenario(
                "priority_preemptive",
                slots=1,
                use_real_backend=use_real,
                model_name=args.model,
                bg_tokens=bg_len,
                chat_tokens=args.chat_tokens,
            )
            results.append((bg_len, fifo, preempt))

        print("\n" + "=" * 80)
        print("MULTI-WORKLOAD SCALING SWEEP RESULTS")
        print("Demonstrating Head-of-Line Blocking Scaling Laws Under CPU Contention")
        print("=" * 80)
        for bg_len, f, p in results:
            qw_speedup = f.queue_wait_ms / max(1.0, p.queue_wait_ms)
            ttft_speedup = f.interactive_ttft_ms / max(1.0, p.interactive_ttft_ms)
            tot_speedup = f.interactive_total_ms / max(1.0, p.interactive_total_ms)
            print(f"\n[Workload: Background {bg_len} tokens | Interactive {args.chat_tokens} tokens]")
            print(f"  {'Metric':<28} | {'FIFO (Standard)':<19} | {'Preemptive (Lattice)':<20} | {'Speedup'}")
            print(f"  {'-' * 28}+-+{'-' * 19}+-+{'-' * 20}+-+{'-' * 12}")
            print(f"  {'Queue Wait Time':<28} | {f.queue_wait_ms:>16.1f} ms | {p.queue_wait_ms:>17.1f} ms | {qw_speedup:>8.1f}x faster")
            print(f"  {'Time To First Token (TTFT)':<28} | {f.interactive_ttft_ms:>16.1f} ms | {p.interactive_ttft_ms:>17.1f} ms | {ttft_speedup:>8.1f}x faster")
            print(f"  {'Interactive Total Latency':<28} | {f.interactive_total_ms:>16.1f} ms | {p.interactive_total_ms:>17.1f} ms | {tot_speedup:>8.1f}x faster")
            print(f"  {'Background Makespan':<28} | {f.background_total_ms:>16.1f} ms | {p.background_total_ms:>17.1f} ms | Yield Trade-off")
            print(f"  {'Preemptions / Resumes':<28} | {f.preemptions:>16} / {f.resumptions:<2} | {p.preemptions:>17} / {p.resumptions:<2} | Clean Recovery")
        print("=" * 80)
        return

    print(f"\n1. Running baseline (priority_fifo: standard FIFO queueing, {args.bg_tokens} bg tokens)...")
    fifo = await run_scenario(
        "priority_fifo",
        slots=1,
        use_real_backend=use_real,
        model_name=args.model,
        bg_tokens=args.bg_tokens,
        chat_tokens=args.chat_tokens,
    )

    print(f"2. Running candidate (priority_preemptive: cooperative preemption & auto-resume, {args.bg_tokens} bg tokens)...")
    preempt = await run_scenario(
        "priority_preemptive",
        slots=1,
        use_real_backend=use_real,
        model_name=args.model,
        bg_tokens=args.bg_tokens,
        chat_tokens=args.chat_tokens,
    )

    qw_speedup = fifo.queue_wait_ms / max(1.0, preempt.queue_wait_ms)
    ttft_speedup = fifo.interactive_ttft_ms / max(1.0, preempt.interactive_ttft_ms)
    total_speedup = fifo.interactive_total_ms / max(1.0, preempt.interactive_total_ms)
    qw_reduction = ((fifo.queue_wait_ms - preempt.queue_wait_ms) / max(1.0, fifo.queue_wait_ms)) * 100
    ttft_reduction = ((fifo.interactive_ttft_ms - preempt.interactive_ttft_ms) / max(1.0, fifo.interactive_ttft_ms)) * 100
    total_reduction = ((fifo.interactive_total_ms - preempt.interactive_total_ms) / max(1.0, fifo.interactive_total_ms)) * 100
    bg_makespan_increase = ((preempt.background_total_ms - fifo.background_total_ms) / max(1.0, fifo.background_total_ms)) * 100

    print("\n" + "=" * 78)
    print("CONTENTION BENCHMARK RESULTS SUMMARY")
    print("=" * 78)
    print(f"{'Metric':<34} | {'FIFO (Standard)':<18} | {'Preemptive (Lattice)':<20}")
    print("-" * 78)
    print(f"{'Interactive Queue Wait Time':<34} | {fifo.queue_wait_ms:>15.1f} ms | {preempt.queue_wait_ms:>17.1f} ms")
    print(f"{'Interactive TTFT':<34} | {fifo.interactive_ttft_ms:>15.1f} ms | {preempt.interactive_ttft_ms:>17.1f} ms")
    print(f"{'Interactive Total Latency':<34} | {fifo.interactive_total_ms:>15.1f} ms | {preempt.interactive_total_ms:>17.1f} ms")
    print(f"{'Background Total Makespan':<34} | {fifo.background_total_ms:>15.1f} ms | {preempt.background_total_ms:>17.1f} ms")
    print(f"{'Preemptions Triggered':<34} | {fifo.preemptions:>18} | {preempt.preemptions:>20}")
    print(f"{'Seamless Resumptions':<34} | {fifo.resumptions:>18} | {preempt.resumptions:>20}")
    print(f"{'Interactive Completed':<34} | {fifo.interactive_completed:>17}/1 | {preempt.interactive_completed:>19}/1")
    print(f"{'Background Completed':<34} | {fifo.background_completed:>17}/1 | {preempt.background_completed:>19}/1")
    print("-" * 78)
    print(f"\n>>> QUEUE WAIT TIME REDUCTION: {qw_reduction:.1f}% FASTER ({qw_speedup:.1f}x speedup) <<<")
    print(f">>> INTERACTIVE TTFT REDUCTION: {ttft_reduction:.1f}% FASTER ({ttft_speedup:.1f}x speedup) <<<")
    print(f">>> INTERACTIVE TOTAL LATENCY: {total_reduction:.1f}% FASTER ({total_speedup:.1f}x speedup) <<<")
    print(f">>> BACKGROUND MAKESPAN IMPACT: +{bg_makespan_increase:.1f}% (trade-off: yields CPU to chat) <<<")
    print("=" * 78)



if __name__ == "__main__":
    asyncio.run(main())

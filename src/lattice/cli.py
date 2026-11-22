"""Baseline operator CLI with explicit backend and strategy metadata."""

import argparse
import asyncio
import datetime
import json
import os
import platform
import sys
from contextlib import aclosing
from pathlib import Path

from pydantic import ValidationError

from .backends import create_backend
from .config import load_settings, public_model, register_model, select_model
from .runtime import Runtime
from .types import GenerationRequest, LatticeError


def parser():
    root = argparse.ArgumentParser(prog="lattice")
    root.add_argument(
        "--config", help="Operator registry JSON (default configs/local.json)"
    )
    commands = root.add_subparsers(dest="command", required=True)
    models = commands.add_parser("models").add_subparsers(dest="action", required=True)
    models.add_parser("list")
    models.add_parser("inspect").add_argument("model")
    for act in ["register", "add"]:
        reg = models.add_parser(act)
        reg.add_argument("source", help="Path to .gguf file or download URL")
        reg.add_argument("--name", help="Custom model ID (default: filename stem)")
        reg.add_argument("--precision", help="Precision override (e.g. Q4_K_M, F16)")
        reg.add_argument(
            "--kv-bytes-per-token",
            type=int,
            help="KV cache memory size in bytes per token",
        )
    for name in ["generate", "serve"]:
        sub = commands.add_parser(name)
        sub.add_argument("--model", required=True)
        sub.add_argument(
            "--host-reserve-mb", type=int, help="Host RAM reserve cap in MB"
        )
        if name == "generate":
            sub.add_argument(
                "--strategy",
                choices=["standard", "cached", "speculative", "adaptive"],
                default="standard",
            )
            sub.add_argument("--draft-model")
            sub.add_argument("--draft-tokens", type=int, default=4)
            sub.add_argument("--max-memory-mb", type=int)
            sub.add_argument("--prompt", required=True)
            sub.add_argument("--max-tokens", type=int, default=64)
            sub.add_argument("--temperature", type=float, default=0.0)
            sub.add_argument("--seed", type=int, default=0)
            sub.add_argument("--timeout", type=float, default=60)
            sub.add_argument("--stream", action="store_true")
            sub.add_argument("--json", action="store_true")
        else:
            sub.add_argument(
                "--preset",
                choices=["chat", "batch", "default"],
                default="default",
                help="Preset profile (chat: preemptive priority + 2 slots + auto-tuned reserve)",
            )
            sub.add_argument("--native-slots", type=int, choices=[1, 2, 3, 4, 8])
            sub.add_argument(
                "--admission-policy",
                choices=[
                    "priority_fifo",
                    "priority_cost",
                    "priority_cost_reserve",
                    "priority_cost_coalesce",
                    "priority_preemptive",
                ],
                help="Opt-in admission experiment; default remains priority_fifo",
            )
            sub.add_argument("--host", default="127.0.0.1")
            sub.add_argument("--port", type=int, default=8000)
    for name in ["benchmark", "profile"]:
        sub = commands.add_parser(name)
        sub.add_argument("--model", required=True)
        sub.add_argument("--output", type=Path)
        sub.add_argument("--trials", type=int)
        sub.add_argument("--warmups", type=int)
        sub.add_argument("--workloads", nargs="+")
        sub.add_argument("--quality", action="store_true")
        sub.add_argument(
            "--workload-file",
            type=Path,
            default=Path("benchmarks/workloads/cpu-v1.json"),
        )
    optimize = commands.add_parser("optimize")
    optimize.add_argument("--model", required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("model_a")
    compare.add_argument("model_b")
    compare.add_argument("--output", type=Path)
    compare.add_argument("--trials", type=int, default=30)
    compare.add_argument("--quality", action="store_true")
    commands.add_parser("system-info")
    for name in ["status", "ps"]:
        scmd = commands.add_parser(name)
        scmd.add_argument("--json", action="store_true", help="Output status as JSON")
    return root


async def run_generation(settings, entry, args):
    if args.draft_model:
        settings.draft_model_id = args.draft_model
    backend = create_backend(settings, entry)
    runtime = Runtime(settings, entry.id, backend)
    request = GenerationRequest(
        model=entry.id,
        prompt=args.prompt,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        seed=args.seed,
        timeout_seconds=args.timeout,
        max_memory_mb=args.max_memory_mb,
        optimization={"mode": args.strategy, "draft_tokens": args.draft_tokens},
    )
    try:
        if args.stream:
            async with aclosing(runtime.events(request)) as events:
                async for event in events:
                    if args.json:
                        print(json.dumps(event), flush=True)
                    elif event["type"] == "token":
                        print(event["text"], end="", flush=True)
                    elif event["type"] == "done":
                        print("\n" + json.dumps(event["record"]), file=sys.stderr)
        else:
            result = await runtime.generate(request)
            if args.json:
                print(json.dumps(result))
            else:
                print(result["text"])
                print(json.dumps(result["metadata"]), file=sys.stderr)
    finally:
        close = getattr(backend, "aclose", None)
        if close:
            await close()
        else:
            backend.stop()


def main():
    args = parser().parse_args()
    try:
        if args.command == "system-info":
            print(
                json.dumps(
                    {
                        "platform": platform.platform(),
                        "python": platform.python_version(),
                        "cpu_count": os.cpu_count(),
                        "execution_target": "cpu",
                        "nvidia_device_detected": any(
                            Path("/dev").glob("nvidia[0-9]*")
                        ),
                        "cuda_enabled": False,
                        "gpu_support": "not tested",
                    },
                    indent=2,
                )
            )
            return
        settings = load_settings(args.config)
        if args.command in ("status", "ps"):
            import urllib.error
            import urllib.request

            from .observability.host import get_host_memory_kb

            mem = get_host_memory_kb()
            total_mb = mem.get("MemTotal", 0) // 1024
            avail_mb = mem.get("MemAvailable", 0) // 1024
            reserve_mb = settings.host_reserve_mb
            headroom_mb = max(0, avail_mb - reserve_mb)

            server_online = False
            active_models = []
            try:
                with urllib.request.urlopen(
                    "http://127.0.0.1:8000/v1/models", timeout=0.5
                ) as resp:
                    if resp.status == 200:
                        server_online = True
                        data = json.loads(resp.read().decode())
                        active_models = [m.get("id") for m in data.get("data", [])]
            except (OSError, urllib.error.URLError):
                pass

            status_data = {
                "server": {
                    "status": "online" if server_online else "offline",
                    "endpoint": "http://127.0.0.1:8000" if server_online else None,
                    "active_models": active_models,
                },
                "host": {
                    "platform": platform.platform(),
                    "cpu_count": os.cpu_count(),
                    "total_memory_mb": total_mb,
                    "available_memory_mb": avail_mb,
                    "host_reserve_mb": reserve_mb,
                    "memory_headroom_mb": headroom_mb,
                },
                "config": {
                    "admission_policy": settings.admission_policy,
                    "native_slots": settings.native_slots,
                    "context_tokens": settings.context_tokens,
                },
                "models": [
                    {
                        "id": m.id,
                        "precision": m.precision,
                        "kv_bytes_per_token": m.kv_bytes_per_token,
                        "kv_cache_ready": m.kv_bytes_per_token is not None,
                    }
                    for m in settings.models
                ],
            }

            if getattr(args, "json", False):
                print(json.dumps(status_data, indent=2))
            else:
                print("=" * 62)
                print("⚡ LATTICE SYSTEM & SERVER STATUS")
                print("=" * 62)
                srv_str = (
                    "🟢 Online (http://127.0.0.1:8000)"
                    if server_online
                    else "⚪ Offline (start with 'lattice serve --preset chat')"
                )
                print(f"Server Status:       {srv_str}")
                if active_models:
                    print(f"Loaded Models:       {', '.join(active_models)}")
                print("-" * 62)
                print(f"Host OS:             {platform.platform()}")
                print(f"CPU Cores:           {os.cpu_count()}")
                print(
                    f"Host Memory:         {avail_mb} MB available / {total_mb} MB total"
                )
                print(
                    f"Safety Reserve:      {reserve_mb} MB (Headroom: {headroom_mb} MB)"
                )
                print("-" * 62)
                print(f"Admission Policy:    {settings.admission_policy}")
                print(f"Native Slots:        {settings.native_slots}")
                print("-" * 62)
                print("Registered Models:")
                for m in settings.models:
                    kv_flag = (
                        f"✅ Ready ({m.kv_bytes_per_token} B/tok)"
                        if m.kv_bytes_per_token
                        else "⚠️ Missing size"
                    )
                    print(f"  • {m.id:<24} [{m.precision}] (Cache: {kv_flag})")
                print("=" * 62)
            return
        if args.command == "models":
            if args.action in ("register", "add"):
                entry = register_model(
                    settings,
                    args.source,
                    name=args.name,
                    precision=args.precision,
                    kv_bytes_per_token=getattr(args, "kv_bytes_per_token", None),
                    save=True,
                    config_path=args.config,
                )
                print(json.dumps(public_model(entry), indent=2))
                return
            data = (
                [public_model(m) for m in settings.models]
                if args.action == "list"
                else public_model(select_model(settings, args.model))
            )
            print(json.dumps(data, indent=2))
            return
        if args.command == "compare":
            from .evaluation.benchmark import run_benchmark

            output = args.output or Path("benchmarks/results") / datetime.datetime.now(
                datetime.UTC
            ).strftime("compare-%Y%m%dT%H%M%S%fZ")
            output.mkdir(parents=True, exist_ok=False)
            for label, model_id in [("a", args.model_a), ("b", args.model_b)]:
                select_model(settings, model_id)
                asyncio.run(
                    run_benchmark(
                        settings,
                        model_id,
                        Path("benchmarks/workloads/cpu-v1.json"),
                        output / label,
                        args.trials,
                        3,
                        ["short", "long_prompt"],
                        Path("benchmarks/datasets/quality-smoke.json")
                        if args.quality
                        else None,
                    )
                )
            print(
                json.dumps(
                    {
                        "output": str(output),
                        "note": "Different model IDs are not a same-weight optimization unless artifact provenance establishes that.",
                    },
                    indent=2,
                )
            )
            return
        entry = select_model(settings, args.model)
        if args.command == "optimize":
            profiles = []
            if settings.policy_file:
                profiles = [
                    p
                    for p in json.loads(Path(settings.policy_file).read_text())[
                        "profiles"
                    ]
                    if p["model_sha256"] == entry.sha256
                    and p["backend_sha256"] == settings.backend_sha256
                ]
            print(
                json.dumps(
                    {
                        "model": entry.id,
                        "backend": "llama.cpp",
                        "default_strategy": "standard",
                        "qualified_profiles": profiles,
                        "automatic_model_or_precision_substitution": False,
                        "note": "Evidence report only; does not modify configuration or relax quality constraints.",
                    },
                    indent=2,
                )
            )
            return
        if args.command in ("benchmark", "profile"):
            from .evaluation.benchmark import run_benchmark

            output = args.output or Path("benchmarks/results") / datetime.datetime.now(
                datetime.UTC
            ).strftime("%Y%m%dT%H%M%S%fZ")
            summary = asyncio.run(
                run_benchmark(
                    settings,
                    entry.id,
                    args.workload_file,
                    output,
                    args.trials
                    if args.trials is not None
                    else (3 if args.command == "profile" else None),
                    args.warmups,
                    args.workloads,
                    Path("benchmarks/datasets/quality-smoke.json")
                    if args.quality
                    else None,
                )
            )
            print(
                json.dumps(
                    {
                        "output": str(output),
                        "workloads": summary["workloads"],
                        "quality": None
                        if summary["quality"] is None
                        else {
                            k: v
                            for k, v in summary["quality"].items()
                            if k != "outcomes"
                        },
                    },
                    indent=2,
                )
            )
        elif args.command == "generate":
            if getattr(args, "host_reserve_mb", None) is not None:
                settings.host_reserve_mb = args.host_reserve_mb
            asyncio.run(run_generation(settings, entry, args))
        elif args.command == "serve":
            import uvicorn

            from .api import create_app
            from .observability.host import get_host_memory_kb

            key = os.environ.get("LATTICE_API_KEY")
            if args.host not in ("127.0.0.1", "localhost", "::1") and not key:
                raise LatticeError(
                    "Set LATTICE_API_KEY before binding a non-loopback interface"
                )
            if getattr(args, "preset", "default") == "chat":
                if args.admission_policy is None:
                    settings.admission_policy = "priority_preemptive"
                if args.native_slots is None:
                    settings.native_slots = 2
                if getattr(args, "host_reserve_mb", None) is None:
                    mem = get_host_memory_kb()
                    total_mb = mem.get("MemTotal", 4096 * 1024) // 1024
                    if total_mb <= 4096:
                        settings.host_reserve_mb = 1024
                print(
                    f"⚡ [Preset: chat enabled] Policy: {settings.admission_policy}, "
                    f"Slots: {settings.native_slots}, Host reserve: {settings.host_reserve_mb}MB",
                    file=sys.stderr,
                )
            if args.native_slots is not None:
                settings.native_slots = args.native_slots
            if args.admission_policy is not None:
                settings.admission_policy = args.admission_policy
            if getattr(args, "host_reserve_mb", None) is not None:
                settings.host_reserve_mb = args.host_reserve_mb
            backend = create_backend(settings, entry)
            factory = (
                None
                if settings.native_slots > 1
                else lambda model: create_backend(settings, model)
            )
            runtime = Runtime(settings, entry.id, backend, backend_factory=factory)
            uvicorn.run(
                create_app(settings, runtime, key),
                host=args.host,
                port=args.port,
                limit_concurrency=32,
                timeout_keep_alive=5,
            )
    except (LatticeError, ValidationError, OSError) as exc:
        print(f"lattice: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()

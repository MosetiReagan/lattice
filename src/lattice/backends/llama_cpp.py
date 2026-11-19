"""Pinned CPU llama.cpp worker. Native kernels/KV/sampling are upstream functionality."""

import asyncio
import contextlib
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx

from lattice.config import ModelEntry, Settings, file_hash
from lattice.types import GenerationRequest, LatticeError


class LlamaCppBackend:
    def __init__(self, settings: Settings, model: ModelEntry):
        self.settings, self.model = settings, model
        self.process: subprocess.Popen | None = None
        self.base_url = ""
        self.key = secrets.token_urlsafe(32)
        self.worker_startup_ms: float | None = None
        self.identity = {
            "name": "llama.cpp",
            "commit": settings.backend_commit,
            "binary_sha256": settings.backend_sha256,
            "model_sha256": model.sha256,
            "precision": model.precision,
            "device": "cpu",
            "strategy": "standard",
        }

    async def start(self) -> None:
        if self.process and self.process.poll() is None:
            return
        started = time.perf_counter()
        for filename, expected in [
            (self.settings.backend_binary, self.settings.backend_sha256),
            (self.model.path, self.model.sha256),
            *self.settings.backend_files.items(),
        ]:
            path = Path(filename)
            if not path.is_file():
                raise LatticeError(
                    "Provision the registered backend and model artifacts first",
                    503,
                    "artifact_missing",
                )
            actual = await asyncio.to_thread(file_hash, path)
            if actual != expected:
                raise LatticeError(
                    "Artifact SHA-256 mismatch; refusing to load",
                    503,
                    "artifact_mismatch",
                )
        # Read host availability, not a promise about resident peak memory.
        mem = {
            k: int(v.split()[0])
            for k, v in (
                line.split(":", 1)
                for line in Path("/proc/meminfo").read_text().splitlines()
            )
        }
        need_kb = Path(self.model.path).stat().st_size // 1024 + 768 * 1024
        if mem.get("MemAvailable", 0) < need_kb + self.settings.host_reserve_mb * 1024:
            raise LatticeError(
                "Insufficient host memory for weights, working estimate and reserve",
                503,
                "memory_admission_failed",
            )
        # A private random port plus random credential prevents attaching to another worker.
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.base_url = f"http://127.0.0.1:{port}"
        log_dir = Path(self.settings.log_directory)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "backend.log"
        fd = os.open(log_path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
        args = [
            self.settings.backend_binary,
            "--model",
            self.model.path,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--api-key",
            self.key,
            "--alias",
            self.model.id,
            "--ctx-size",
            str(self.settings.context_tokens),
            "--threads",
            str(self.settings.threads),
            "--threads-batch",
            str(self.settings.threads),
            "--parallel",
            "1",
            "--n-gpu-layers",
            "0",
            "--batch-size",
            "256",
            "--ubatch-size",
            "256",
            "--cache-type-k",
            "f16",
            "--cache-type-v",
            "f16",
            "--no-cache-prompt",
            "--no-context-shift",
            "--spec-type",
            "none",
            "--no-slots",
            "--offline",
            "--no-ui",
            "--no-warmup",
        ]
        env = {k: v for k, v in os.environ.items() if not k.startswith("LLAMA_ARG_")}
        try:
            # Only process creation is synchronous; no preexec_fn or waiting here.
            self.process = subprocess.Popen(  # noqa: ASYNC220
                [
                    sys.executable,
                    "-m",
                    "lattice.worker",
                    str(self.settings.worker_address_space_mb),
                    *args,
                ],
                stdin=subprocess.DEVNULL,
                stdout=fd,
                stderr=fd,
                env=env,
                start_new_session=True,
            )
        finally:
            os.close(fd)
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=1) as client:
                deadline = time.monotonic() + self.settings.startup_timeout_seconds
                while time.monotonic() < deadline:
                    if self.process.poll() is not None:
                        raise LatticeError(
                            "Backend exited during startup; inspect operator backend.log",
                            503,
                            "backend_start_failed",
                        )
                    try:
                        reply = await client.get(
                            self.base_url + "/health", headers=self.headers
                        )
                        if reply.status_code == 200:
                            self.worker_startup_ms = (
                                time.perf_counter() - started
                            ) * 1000
                            return
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.1)
            raise LatticeError(
                "Backend startup timed out", 503, "backend_start_timeout"
            )
        except BaseException:
            self.stop()
            raise

    @property
    def headers(self) -> dict:
        return {"Authorization": "Bearer " + self.key}

    def stop(self) -> None:
        process, self.process = self.process, None
        if process and process.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)

    async def _post(self, client: httpx.AsyncClient, endpoint: str, body: dict) -> dict:
        response = await client.post(endpoint, json=body)
        if response.status_code != 200:
            raise LatticeError("Backend rejected the request", 502, "backend_error")
        return response.json()

    async def events(self, request: GenerationRequest) -> AsyncIterator[dict]:
        await self.start()
        completed = False
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.headers,
                timeout=None,
                trust_env=False,
            ) as client:
                prompt = request.prompt
                if request.messages is not None:
                    formatted = await self._post(
                        client,
                        "/apply-template",
                        {"messages": [m.model_dump() for m in request.messages]},
                    )
                    prompt = formatted["prompt"]
                encoded = await self._post(
                    client,
                    "/tokenize",
                    {"content": prompt, "add_special": True, "parse_special": True},
                )
                token_ids = encoded["tokens"]
                if len(token_ids) + request.max_tokens > self.settings.context_tokens:
                    completed = (
                        True  # No generation was submitted; worker can remain alive.
                    )
                    raise LatticeError(
                        "Prompt plus output exceeds context limit; no input was truncated",
                        400,
                        "context_limit",
                    )
                yield {"type": "prefill", "prompt_tokens": len(token_ids)}
                # Pass exact token IDs: validation and inference use the same tokenization.
                body = {
                    "prompt": token_ids,
                    "n_predict": request.max_tokens,
                    "stream": True,
                    "temperature": request.temperature,
                    "seed": request.seed,
                    "top_k": 0,
                    "top_p": 1.0,
                    "min_p": 0.0,
                    "repeat_penalty": 1.0,
                    "presence_penalty": 0.0,
                    "frequency_penalty": 0.0,
                    "samplers": ["temperature"],
                    "cache_prompt": False,
                    "return_tokens": True,
                }
                count = 0
                async with client.stream("POST", "/completion", json=body) as response:
                    if response.status_code != 200:
                        raise LatticeError(
                            "Backend generation failed", 502, "backend_error"
                        )
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        raw = json.loads(line[6:])
                        if "error" in raw:
                            raise LatticeError(
                                "Backend stream failed", 502, "backend_error"
                            )
                        if raw.get("stop"):
                            if (
                                raw.get("truncated")
                                or raw.get("tokens_predicted", count)
                                > request.max_tokens
                            ):
                                raise LatticeError(
                                    "Backend violated context/output limit",
                                    502,
                                    "backend_limit_violation",
                                )
                            completed = True
                            yield {
                                "type": "backend_done",
                                "completion_tokens": raw.get("tokens_predicted", count),
                                "finish_reason": "length"
                                if raw.get("stop_type") == "limit"
                                else "stop",
                                "backend_timings": raw.get("timings", {}),
                                "tokens_cached": raw.get("tokens_cached", 0),
                            }
                            return
                        tokens = raw.get("tokens", [])
                        count += len(tokens)
                        # Upstream may finish a multibyte character past n_predict. Never emit that chunk.
                        if count > request.max_tokens:
                            raise LatticeError(
                                "Backend exceeded hard output limit; stream aborted",
                                502,
                                "backend_limit_violation",
                            )
                        yield {
                            "type": "token",
                            "text": raw.get("content", ""),
                            "token_ids": tokens,
                        }
                raise LatticeError(
                    "Backend stream ended without a terminal event",
                    502,
                    "backend_stream_incomplete",
                )
        except httpx.HTTPError as exc:
            raise LatticeError(
                "Backend connection failed", 502, "backend_unavailable"
            ) from exc
        finally:
            if not completed:
                # Single-flight baseline: kill owns cancellation semantics, not an assumed HTTP close.
                # Next admitted request starts a fresh worker. Queued requests keep their deadlines.
                self.stop()

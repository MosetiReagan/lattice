"""Pinned CPU llama.cpp worker. Native kernels/KV/sampling are upstream functionality."""

import asyncio
import contextlib
import hashlib
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from collections.abc import AsyncIterator
from dataclasses import asdict
from pathlib import Path

import httpx

from lattice.cache.prefix import CacheIdentity, PrefixCache
from lattice.config import ModelEntry, Settings, file_hash, select_model
from lattice.controller.policy import Features, PathEvidence, RuleController
from lattice.observability.hardware import cpu_fingerprint
from lattice.optimizations.speculative.compatibility import tokenizer_fingerprint
from lattice.scheduler.budget import Budget, ResourceSnapshot
from lattice.types import GenerationRequest, LatticeError


class LlamaCppBackend:
    native_slots = 1

    def __init__(self, settings: Settings, model: ModelEntry):
        self.settings, self.model = settings, model
        self.process: subprocess.Popen | None = None
        self.base_url = ""
        self._strategy = "standard"
        self._memory_cap = settings.worker_address_space_mb
        self._queue_depth = 0
        self._cpu_fingerprint = cpu_fingerprint()
        profiles = []
        if settings.policy_file:
            for row in json.loads(Path(settings.policy_file).read_text())["profiles"]:
                if row.get("qualified_prompt_sha256") is not None:
                    row["qualified_prompt_sha256"] = frozenset(
                        row["qualified_prompt_sha256"]
                    )
                profiles.append(PathEvidence(**row))
        self.controller = RuleController(profiles)
        self.policy_sha256 = (
            file_hash(Path(settings.policy_file)) if settings.policy_file else None
        )
        self._draft = None
        self._draft_tokens = settings.draft_tokens
        self._compatibility = {}
        self._tokenizer_sha = None
        self.prefix = PrefixCache(
            settings.cache_limit_mb * 1024**2,
            model.kv_bytes_per_token or 1,
            min_tokens=settings.cache_min_tokens,
        )
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

    def set_queue_depth(self, depth: int) -> None:
        self._queue_depth = depth

    async def configure(self, request: GenerationRequest) -> str | None:
        if request.optimization.profile == "lowest_compute":
            raise LatticeError(
                "Compute-cost modeling is not yet qualified",
                422,
                "compute_model_unavailable",
            )
        strategy = request.optimization.mode
        if strategy == "adaptive":
            strategy = "standard"
        memory_cap = min(
            request.max_memory_mb or self.settings.worker_address_space_mb,
            self.settings.worker_address_space_mb,
        )
        if memory_cap != self._memory_cap:
            self.stop()
        self._memory_cap = memory_cap
        reason = None
        draft = None
        if strategy == "speculative":
            if request.temperature != 0:
                reason = (
                    "Native speculative serving is verified for greedy decoding only"
                )
            elif not self.settings.draft_model_id:
                reason = "No draft model is configured"
            else:
                try:
                    draft = select_model(self.settings, self.settings.draft_model_id)
                    key = (self.model.sha256, draft.sha256)
                    if key not in self._compatibility:
                        self._compatibility[key] = await asyncio.to_thread(
                            tokenizer_fingerprint, Path(self.model.path)
                        ) == await asyncio.to_thread(
                            tokenizer_fingerprint, Path(draft.path)
                        )
                    if not self._compatibility[key]:
                        reason = "Draft and target tokenizer metadata are not identical"
                except (LatticeError, OSError, ValueError):
                    reason = "Configured draft artifact is unavailable or incompatible"
            if reason:
                if not request.optimization.allow_fallback:
                    raise LatticeError(reason, 422, "incompatible_strategy")
                strategy, draft = "standard", None
        draft_tokens = request.optimization.draft_tokens or self.settings.draft_tokens
        if (strategy == "speculative") != (self._strategy == "speculative") or (
            strategy == "speculative" and draft_tokens != self._draft_tokens
        ):
            self.stop()
        self._strategy, self._draft, self._draft_tokens = strategy, draft, draft_tokens
        self.identity["strategy"] = strategy
        self.identity["draft_model_sha256"] = draft.sha256 if draft else None
        return reason

    async def start(self) -> None:
        if self.process and self.process.poll() is None:
            return
        started = time.perf_counter()
        for filename, expected in [
            (self.settings.backend_binary, self.settings.backend_sha256),
            (self.model.path, self.model.sha256),
            *self.settings.backend_files.items(),
            *(([(self._draft.path, self._draft.sha256)]) if self._draft else []),
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
        need_kb = (
            Path(self.model.path).stat().st_size
            + (Path(self._draft.path).stat().st_size if self._draft else 0)
        ) // 1024 + 768 * 1024
        if self.native_slots > 1:
            need_kb += (
                (self.native_slots - 1)
                * self.settings.context_tokens
                * (self.model.kv_bytes_per_token or 0)
                // 1024
            )
        if need_kb > self._memory_cap * 1024:
            raise LatticeError(
                "Weights plus working estimate exceed worker address-space cap",
                422,
                "budget_infeasible",
            )
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
            str(self.settings.context_tokens * self.native_slots),
            "--threads",
            str(self.settings.threads),
            "--threads-batch",
            str(self.settings.threads),
            "--parallel",
            str(self.native_slots),
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
            "draft-simple" if self._draft else "none",
            "--metrics",
            "--slots" if self.native_slots > 1 else "--no-slots",
            "--offline",
            "--no-ui",
            "--no-warmup",
        ]
        if self._draft:
            args.extend(
                [
                    "--model-draft",
                    self._draft.path,
                    "--spec-draft-n-max",
                    str(self._draft_tokens),
                    "--spec-draft-n-min",
                    "1",
                    "--spec-draft-threads",
                    str(self.settings.threads),
                ]
            )
        env = {k: v for k, v in os.environ.items() if not k.startswith("LLAMA_ARG_")}
        try:
            # Only process creation is synchronous; no preexec_fn or waiting here.
            self.process = subprocess.Popen(  # noqa: ASYNC220
                [
                    sys.executable,
                    "-m",
                    "lattice.worker",
                    str(self._memory_cap),
                    str(os.getpid()),
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
        self.prefix.invalidate()
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

    def completion_headers(self, execution_context=None) -> dict:
        return {}

    def completion_payload(self, body: dict, execution_context=None) -> dict:
        return body

    def completion_response(self, execution_context=None) -> None:
        pass

    async def abort_generation(self) -> None:
        self.stop()

    async def events(
        self, request: GenerationRequest, execution_context=None
    ) -> AsyncIterator[dict]:
        fallback = await self.configure(request)
        try:
            await self.start()
        except LatticeError as exc:
            if (
                self._strategy != "speculative"
                or not request.optimization.allow_fallback
                or exc.code not in ("budget_infeasible", "memory_admission_failed")
            ):
                raise
            self.stop()
            standard = request.model_copy(deep=True)
            standard.optimization.mode = "standard"
            await self.configure(standard)
            await self.start()
            fallback = "Draft exceeds available memory budget; target standard execution preserved"
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
                cache_identity = CacheIdentity(
                    "single-operator",
                    self.model.sha256,
                    self._tokenizer_sha or self.model.sha256,
                    self.settings.backend_sha256,
                    self.settings.context_tokens,
                    "f16",
                    "artifact-default-rope-mask",
                )
                policy = None
                if request.optimization.mode == "adaptive":
                    preview = self.prefix.plan(
                        cache_identity, tuple(token_ids), count=False
                    )
                    meminfo = dict(
                        line.split(":", 1)
                        for line in Path("/proc/meminfo").read_text().splitlines()
                    )
                    resources = ResourceSnapshot(
                        int(meminfo["MemAvailable"].split()[0]) // 1024,
                        self.settings.host_reserve_mb,
                        self._queue_depth,
                    )
                    policy = self.controller.choose(
                        Features(
                            len(token_ids),
                            request.max_tokens,
                            preview.prefix_tokens,
                            self.model.sha256,
                            self.settings.backend_sha256,
                            request.temperature,
                            self._queue_depth,
                            hashlib.sha256(prompt.encode()).hexdigest(),
                            self.settings.threads,
                            self._cpu_fingerprint,
                        ),
                        Budget(
                            request.max_tokens,
                            request.max_memory_mb,
                            request.latency_budget_ms,
                            request.max_estimated_compute_ms,
                        ),
                        resources,
                        preference=request.optimization.profile,
                    )
                    self._strategy = policy.strategy
                    self.identity["strategy"] = self._strategy
                if request.max_estimated_compute_ms is not None and policy is None:
                    raise LatticeError(
                        "An estimated-compute budget requires a qualified adaptive profile",
                        422,
                        "budget_infeasible",
                    )
                cache_allowed = (
                    self._strategy == "cached"
                    and self.model.kv_bytes_per_token is not None
                )
                if self._strategy == "cached" and not cache_allowed:
                    raise LatticeError(
                        "KV byte accounting is unknown for this model",
                        422,
                        "cache_accounting_unknown",
                    )
                decision = (
                    self.prefix.plan(cache_identity, tuple(token_ids))
                    if cache_allowed
                    else None
                )
                if not cache_allowed:
                    self.prefix.invalidate()
                yield {
                    "type": "prefill",
                    "prompt_tokens": len(token_ids),
                    "strategy": self._strategy,
                    "fallback_reason": fallback,
                    "backend": dict(self.identity),
                    "policy": {
                        **asdict(policy),
                        "evidence_file_sha256": self.policy_sha256,
                    }
                    if policy
                    else None,
                }
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
                    "cache_prompt": bool(decision and decision.reuse),
                    "return_tokens": True,
                }
                count = 0
                body = self.completion_payload(body, execution_context)
                async with client.stream(
                    "POST",
                    "/completion",
                    json=body,
                    headers=self.completion_headers(execution_context),
                ) as response:
                    self.completion_response(execution_context)
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
                            if cache_allowed or request.optimization.mode == "adaptive":
                                self.prefix.remember(cache_identity, tuple(token_ids))
                                self.prefix.observe(
                                    raw.get("timings", {}).get("cache_n", 0)
                                )
                            yield {
                                "type": "backend_done",
                                "completion_tokens": raw.get("tokens_predicted", count),
                                "finish_reason": "length"
                                if raw.get("stop_type") == "limit"
                                else "stop",
                                "backend_timings": raw.get("timings", {}),
                                "tokens_cached": raw.get("timings", {}).get(
                                    "cache_n", 0
                                ),
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
                # Serial mode terminates the worker. Concurrent mode overrides this hook
                # and verifies cancellation through its private native session/slot controls.
                await self.abort_generation()

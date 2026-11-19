"""Single-flight admission and truthful per-request execution records."""

import asyncio
import datetime
import json
import logging
import os
import time
import uuid
from collections import Counter, deque
from collections.abc import AsyncIterator, Callable
from contextlib import aclosing
from pathlib import Path

from .backends import Backend
from .config import ModelEntry, Settings, select_model
from .scheduler.fair import FairSemaphore
from .types import GenerationRequest, LatticeError


class Runtime:
    def __init__(
        self,
        settings: Settings,
        model_id: str,
        backend: Backend,
        backend_factory: Callable[[ModelEntry], Backend] | None = None,
    ):
        self.settings, self.model_id, self.backend = settings, model_id, backend
        self.backend_factory = backend_factory
        if settings.native_slots > 1 and backend_factory is not None:
            raise ValueError(
                "Concurrent serving pins one model; model swapping requires serial admission"
            )
        if settings.native_slots > getattr(backend, "native_slots", 1):
            raise ValueError("Admission capacity exceeds backend slot capacity")
        self.lock = FairSemaphore(settings.native_slots)
        self.waiting = 0
        self.counters: Counter = Counter()
        self.recent: deque = deque(maxlen=100)

    def metrics(self) -> dict:
        return {
            "counters": dict(self.counters),
            "queue_depth": self.waiting,
            "active_requests": self.lock.active,
            "max_active_requests": self.settings.native_slots,
            "backend_slots": getattr(self.backend, "slot_stats", lambda: None)(),
            "recent": list(self.recent),
            "unavailable": [
                "gpu_memory",
                "gpu_utilization",
                "energy",
                "peak_cpu_memory",
                "inter_token_latency",
            ],
            "note": "Client TTFT and chunk intervals are not backend prefill or token intervals.",
        }

    def record(self, item: dict) -> None:
        # Contains no input/output text, native prompt fields, paths or credentials.
        self.recent.append(item)
        self.counters[item["status"]] += 1
        try:
            directory = Path(self.settings.log_directory)
            directory.mkdir(parents=True, exist_ok=True)
            fd = os.open(
                directory / "requests.jsonl",
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o600,
            )
            with os.fdopen(fd, "a") as output:
                output.write(json.dumps(item, allow_nan=False) + "\n")
        except OSError as exc:
            self.counters["audit_write_failed"] += 1
            logging.getLogger(__name__).error(
                "Audit write failed with errno=%s", exc.errno
            )

    async def events(self, request: GenerationRequest) -> AsyncIterator[dict]:
        if self.backend_factory is not None:
            select_model(self.settings, request.model)
        elif request.model != self.model_id:
            raise LatticeError(
                "This worker serves a different model; no routing was performed",
                404,
                "model_not_served",
            )
        if self.lock.locked() and self.waiting >= self.settings.max_queue:
            self.counters["rejected_queue_full"] += 1
            raise LatticeError("Request queue is full; retry later", 429, "queue_full")
        request_id = "lattice-" + uuid.uuid4().hex
        start = time.perf_counter()
        self.waiting += 1
        acquired = False
        queued = True
        record = {
            "id": request_id,
            "created_utc": datetime.datetime.now(datetime.UTC).isoformat(),
            "model": request.model,
            "backend": None,
            "strategy": None,
            "status": "cancelled",
            "queue_wait_ms": None,
            "client_ttft_ms": None,
            "total_ms": None,
            "prompt_tokens": None,
            "completion_tokens": 0,
            "max_tokens": request.max_tokens,
            "priority": request.priority,
            "max_memory_mb": request.max_memory_mb,
            "latency_budget_ms": request.latency_budget_ms,
            "temperature": request.temperature,
            "seed": request.seed,
            "context_tokens": self.settings.context_tokens,
            "backend_timings": None,
            "chunk_intervals_ms": [],
            "quality": None,
        }
        previous_chunk = None
        try:
            async with asyncio.timeout(request.timeout_seconds):
                await self.lock.acquire(request.priority)
                acquired = True
                if request.model != self.model_id:
                    self.backend.stop()
                    self.backend = self.backend_factory(
                        select_model(self.settings, request.model)
                    )
                    self.model_id = request.model
                self.waiting -= 1
                queued = False
                record["queue_depth_at_admission"] = self.waiting
                update_queue = getattr(self.backend, "set_queue_depth", None)
                if update_queue:
                    update_queue(self.waiting)
                record["queue_wait_ms"] = (time.perf_counter() - start) * 1000
                async with aclosing(self.backend.events(request)) as stream:
                    async for event in stream:
                        if event["type"] == "prefill":
                            record["prompt_tokens"] = event["prompt_tokens"]
                            record["strategy"] = event.get("strategy", "standard")
                            record["backend"] = event.get(
                                "backend", dict(self.backend.identity)
                            )
                            record["fallback_reason"] = event.get("fallback_reason")
                            record["policy"] = event.get("policy")
                            record["native_slot"] = event.get("native_slot")
                            record["native_slots"] = event.get("native_slots", 1)
                            record["worker_startup_ms"] = getattr(
                                self.backend, "worker_startup_ms", None
                            )
                            yield {
                                "type": "start",
                                "id": request_id,
                                "model": self.model_id,
                                "strategy": record["strategy"],
                                "backend": record["backend"],
                            }
                        elif event["type"] == "token":
                            now = time.perf_counter()
                            record["completion_tokens"] += len(event["token_ids"])
                            if event["text"]:
                                if record["client_ttft_ms"] is None:
                                    record["client_ttft_ms"] = (now - start) * 1000
                                if previous_chunk is not None:
                                    record["chunk_intervals_ms"].append(
                                        (now - previous_chunk) * 1000
                                    )
                                previous_chunk = now
                            yield event
                        elif event["type"] == "backend_done":
                            record.update(
                                status="completed",
                                completion_tokens=event["completion_tokens"],
                                backend_timings=event["backend_timings"],
                            )
                            record["finish_reason"] = event["finish_reason"]
                            record["tokens_cached"] = event.get("tokens_cached", 0)
                if record["status"] != "completed":
                    raise LatticeError(
                        "Generation ended without a completion",
                        502,
                        "incomplete_generation",
                    )
        except TimeoutError as exc:
            record["status"] = "timeout"
            raise LatticeError(
                "Request deadline exceeded, including queue wait",
                504,
                "request_timeout",
            ) from exc
        except LatticeError as exc:
            record["status"] = "error"
            record["error_code"] = exc.code
            raise
        except (asyncio.CancelledError, GeneratorExit):
            record["status"] = "cancelled"
            raise
        except Exception as exc:
            record["status"] = "error"
            record["error_code"] = "internal_error"
            raise LatticeError(
                "Request failed; consult operator logs", 500, "internal_error"
            ) from exc
        finally:
            if queued:
                self.waiting -= 1
            if acquired:
                self.lock.release()
            record["total_ms"] = (time.perf_counter() - start) * 1000
            record["latency_budget_met"] = (
                None
                if request.latency_budget_ms is None
                else record["total_ms"] <= request.latency_budget_ms
            )
            self.record(record)
        yield {"type": "done", "record": record}

    async def generate(self, request: GenerationRequest) -> dict:
        chunks, tokens, record = [], [], None
        async with aclosing(self.events(request)) as stream:
            async for event in stream:
                if event["type"] == "token":
                    chunks.append(event["text"])
                    tokens.extend(event["token_ids"])
                if event["type"] == "done":
                    record = event["record"]
        return {"text": "".join(chunks), "token_ids": tokens, "metadata": record}

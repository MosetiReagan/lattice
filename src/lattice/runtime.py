"""Single-flight admission and truthful per-request execution records."""

import asyncio
import datetime
import json
import os
import time
import uuid
from collections import Counter, deque
from collections.abc import AsyncIterator
from contextlib import aclosing
from pathlib import Path

from .backends import Backend
from .config import Settings
from .types import GenerationRequest, LatticeError


class Runtime:
    def __init__(self, settings: Settings, model_id: str, backend: Backend):
        self.settings, self.model_id, self.backend = settings, model_id, backend
        self.lock = asyncio.Lock()
        self.waiting = 0
        self.counters: Counter = Counter()
        self.recent: deque = deque(maxlen=100)

    def metrics(self) -> dict:
        return {
            "counters": dict(self.counters),
            "queue_depth": self.waiting,
            "active_requests": int(self.lock.locked()),
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
        directory = Path(self.settings.log_directory)
        directory.mkdir(parents=True, exist_ok=True)
        fd = os.open(
            directory / "requests.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600
        )
        with os.fdopen(fd, "a") as output:
            output.write(json.dumps(item, allow_nan=False) + "\n")
        self.recent.append(item)
        self.counters[item["status"]] += 1

    async def events(self, request: GenerationRequest) -> AsyncIterator[dict]:
        if request.model != self.model_id:
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
            "backend": dict(self.backend.identity),
            "strategy": "standard",
            "status": "cancelled",
            "queue_wait_ms": None,
            "client_ttft_ms": None,
            "total_ms": None,
            "prompt_tokens": None,
            "completion_tokens": 0,
            "max_tokens": request.max_tokens,
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
                await self.lock.acquire()
                acquired = True
                self.waiting -= 1
                queued = False
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

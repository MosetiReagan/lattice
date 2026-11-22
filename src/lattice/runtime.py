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
        is_preemptive = settings.admission_policy == "priority_preemptive"
        self.lock = FairSemaphore(
            settings.native_slots,
            cost_aware=settings.admission_policy
            not in ("priority_fifo", "priority_preemptive"),
            preemptive=is_preemptive,
        )
        if (
            settings.admission_policy == "priority_cost_reserve"
            and settings.native_slots < 2
        ):
            raise ValueError("Reserved admission requires at least two native slots")
        self.bulk_lock = (
            FairSemaphore(settings.native_slots - 1, cost_aware=True)
            if settings.admission_policy == "priority_cost_reserve"
            else None
        )
        self._small_pending = 0
        self._small_drained = asyncio.Event()
        self._small_drained.set()
        self.waiting = 0
        self.counters: Counter = Counter()
        self.recent: deque = deque(maxlen=100)

    def metrics(self) -> dict:
        return {
            "counters": dict(self.counters),
            "queue_depth": self.waiting,
            "active_requests": self.lock.active,
            "max_active_requests": self.settings.native_slots,
            "admission_policy": self.settings.admission_policy,
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
        # Grace/drain waiters also consume admission capacity while native slots
        # may still be free. Bound all outstanding work, not just lock waiters.
        if (
            self.waiting + self.lock.active
            >= self.settings.max_queue + self.settings.native_slots
        ):
            self.counters["rejected_queue_full"] += 1
            raise LatticeError("Request queue is full; retry later", 429, "queue_full")
        request_id = "lattice-" + uuid.uuid4().hex
        start = time.perf_counter()
        self.waiting += 1
        acquired = False
        bulk_acquired = False
        small_registered = False
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
            "admission_policy": self.settings.admission_policy,
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
        is_preemptive = self.settings.admission_policy == "priority_preemptive"
        auto_resume = getattr(self.settings, "preemption_auto_resume", True)
        accumulated_text = ""
        current_request = request
        permit = None
        try:
            async with asyncio.timeout(request.timeout_seconds):
                while True:
                    if self.settings.admission_policy not in (
                        "priority_fifo",
                        "priority_preemptive",
                    ):
                        input_bytes = (
                            len(current_request.prompt.encode())
                            if current_request.prompt is not None
                            else sum(
                                len(message.content.encode())
                                for message in current_request.messages or []
                            )
                        )
                        # A deterministic workload-size proxy, not a validated compute
                        # forecast or task-complexity assessment. Priorities and aging
                        # outrank this tiebreaker. Limits and model/sampling stay fixed.
                        estimated_work = input_bytes + 64 * current_request.max_tokens
                        is_bulk = input_bytes > 1024 or current_request.max_tokens > 32
                        if (
                            self.settings.admission_policy == "priority_cost_coalesce"
                            and is_bulk
                            and current_request.priority == 0
                        ):
                            # Opt-in bounded burst shaping. A short grace interval
                            # lets small requests enter native slots before expensive
                            # prefills; it is included in the original timeout/budget.
                            await asyncio.sleep(0.05)
                        # An explicit higher priority bypasses the bulk lane; this
                        # preserves caller ordering rather than inferring task value.
                        if self.bulk_lock is not None:
                            if is_bulk and current_request.priority == 0:
                                await self.bulk_lock.acquire(
                                    current_request.priority, estimated_work
                                )
                                bulk_acquired = True
                                # Bound the drain hold so sustained small traffic
                                # cannot indefinitely stop bulk admissions.
                                try:
                                    await asyncio.wait_for(
                                        self._small_drained.wait(), 5.0
                                    )
                                except TimeoutError:
                                    pass
                            else:
                                self._small_pending += 1
                                small_registered = True
                                self._small_drained.clear()
                        permit = await self.lock.acquire(
                            current_request.priority, estimated_work
                        )
                    else:
                        permit = await self.lock.acquire(current_request.priority)
                    acquired = True
                    if current_request.model != self.model_id:
                        self.backend.stop()
                        self.backend = self.backend_factory(
                            select_model(self.settings, current_request.model)
                        )
                        self.model_id = current_request.model
                    if queued:
                        self.waiting -= 1
                        queued = False
                    record["queue_depth_at_admission"] = self.waiting
                    update_queue = getattr(self.backend, "set_queue_depth", None)
                    if update_queue:
                        update_queue(self.waiting)
                    if record["queue_wait_ms"] is None:
                        record["queue_wait_ms"] = (time.perf_counter() - start) * 1000

                    preempted_during_stream = False
                    async with aclosing(self.backend.events(current_request)) as stream:
                        async for event in stream:
                            if event["type"] == "prefill":
                                if record["prompt_tokens"] is None:
                                    record["prompt_tokens"] = event["prompt_tokens"]
                                    record["strategy"] = event.get(
                                        "strategy", "standard"
                                    )
                                    record["backend"] = event.get(
                                        "backend", dict(self.backend.identity)
                                    )
                                    record["fallback_reason"] = event.get(
                                        "fallback_reason"
                                    )
                                    record["policy"] = event.get("policy")
                                    record["native_slot"] = event.get("native_slot")
                                    record["native_slots"] = event.get(
                                        "native_slots", 1
                                    )
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
                                    accumulated_text += event["text"]
                                    if record["client_ttft_ms"] is None:
                                        record["client_ttft_ms"] = (now - start) * 1000
                                    if previous_chunk is not None:
                                        record["chunk_intervals_ms"].append(
                                            (now - previous_chunk) * 1000
                                        )
                                    previous_chunk = now
                                yield event
                                if is_preemptive and getattr(
                                    permit, "is_preempted", False
                                ):
                                    preempted_during_stream = True
                                    record["preempted"] = True
                                    self.counters["requests_preempted"] += 1
                                    break
                            elif event["type"] == "backend_done":
                                record.update(
                                    status="completed",
                                    completion_tokens=record["completion_tokens"],
                                    backend_timings=event["backend_timings"],
                                )
                                record["finish_reason"] = event["finish_reason"]
                                record["tokens_cached"] = event.get("tokens_cached", 0)

                    if preempted_during_stream:
                        self.lock.release(permit)
                        acquired = False
                        if not auto_resume:
                            record["status"] = "completed"
                            record["finish_reason"] = "preempted"
                            yield {
                                "type": "backend_done",
                                "completion_tokens": record["completion_tokens"],
                                "finish_reason": "preempted",
                                "backend_timings": {},
                            }
                            break
                        rem = request.max_tokens - record["completion_tokens"]
                        if rem <= 0:
                            record["status"] = "completed"
                            record["finish_reason"] = "length"
                            yield {
                                "type": "backend_done",
                                "completion_tokens": record["completion_tokens"],
                                "finish_reason": "length",
                                "backend_timings": {},
                            }
                            break
                        self.counters["requests_resumed"] += 1
                        record["resumed"] = True
                        from .types import Message

                        current_request = request.model_copy(deep=True)
                        if current_request.prompt is not None:
                            current_request.prompt = (
                                current_request.prompt + accumulated_text
                            )
                        elif current_request.messages is not None:
                            current_request.messages.append(
                                Message(role="assistant", content=accumulated_text)
                            )
                        current_request.max_tokens = rem
                        continue
                    else:
                        break

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
                self.lock.release(permit)
            if bulk_acquired:
                self.bulk_lock.release()
            if small_registered:
                self._small_pending -= 1
                if self._small_pending == 0:
                    self._small_drained.set()
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

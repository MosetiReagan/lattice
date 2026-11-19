"""Immutable multi-slot llama.cpp worker with per-request native cancellation.

Uses the pinned backend's stream-session DELETE and slot state as cancellation
acknowledgement. Neither token batching nor attention kernels are implemented here.
"""

import asyncio
import contextlib
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from lattice.config import ModelEntry, Settings
from lattice.types import GenerationRequest, LatticeError

from .llama_cpp import LlamaCppBackend


@dataclass(eq=False)
class SlotLease:
    slot: int
    conversation: str
    pid: int | None = None
    submitted: bool = False
    acknowledged: bool = False
    completed: bool = False
    released: bool = False


class BatchedLlamaBackend(LlamaCppBackend):
    """Pins model, precision, memory ceiling and standard execution for all slots."""

    def __init__(self, settings: Settings, model: ModelEntry):
        if settings.native_slots < 2:
            raise ValueError("Batched backend requires at least two native slots")
        if model.kv_bytes_per_token is None:
            raise LatticeError(
                "Concurrent KV memory accounting is unknown for this model",
                422,
                "concurrent_memory_accounting_unknown",
            )
        super().__init__(settings, model)
        self.native_slots = settings.native_slots
        self.identity["native_slots"] = self.native_slots
        self._available = asyncio.Queue(maxsize=self.native_slots)
        for slot in range(self.native_slots):
            self._available.put_nowait(slot)
        self._leases: dict[int, SlotLease] = {}
        self._live: set[SlotLease] = set()
        self._quarantined: set[SlotLease] = set()
        self._cleanup_tasks: set[asyncio.Task] = set()
        self._startup_task: asyncio.Task | None = None
        self._verified_pid: int | None = None
        self._verified_cancellations = 0
        self._unconfirmed_cancellations = 0
        self._retirements = 0

    async def start(self) -> None:
        if self._startup_task is None or self._startup_task.done():
            if (
                self.process
                and self.process.poll() is None
                and self._verified_pid == self.process.pid
            ):
                return
            self._startup_task = asyncio.create_task(self._start_and_verify())
        # A disconnect must not cancel shared startup while another admitted request waits.
        await asyncio.shield(self._startup_task)

    async def _start_and_verify(self) -> None:
        await super().start()
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, headers=self.headers, timeout=2, trust_env=False
            ) as client:
                slots = await client.get("/slots")
                slots.raise_for_status()
                rows = slots.json()
                if len(rows) != self.native_slots or {r["id"] for r in rows} != set(
                    range(self.native_slots)
                ):
                    raise ValueError(
                        "Native slot layout differs from configured admission capacity"
                    )
                if any(r["n_ctx"] != self.settings.context_tokens for r in rows):
                    raise ValueError(
                        "Native per-slot context differs from the configured request limit"
                    )
                lookup = await client.post(
                    "/v1/streams/lookup", json={"conversation_ids": []}
                )
                lookup.raise_for_status()
                if lookup.json() != []:
                    raise ValueError("Unexpected private stream lookup response")
                deleted = await client.delete(
                    "/v1/stream",
                    params={"conv_id": "lattice-probe-" + uuid.uuid4().hex},
                )
                if deleted.status_code != 204:
                    raise ValueError(
                        "Native stream cancellation endpoint is unavailable"
                    )
            self._verified_pid = self.process.pid
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            self.stop()
            raise LatticeError(
                "Backend lacks verified slot/context/session cancellation controls",
                503,
                "concurrent_backend_unsupported",
            ) from exc

    def stop(self) -> None:
        self._verified_pid = None
        task = self._startup_task
        with contextlib.suppress(RuntimeError):
            if task and task is not asyncio.current_task() and not task.done():
                task.cancel()
        super().stop()
        for lease in list(self._quarantined):
            self._release(lease)

    async def aclose(self) -> None:
        self.stop()
        tasks = list(self._cleanup_tasks)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._startup_task:
            await asyncio.gather(self._startup_task, return_exceptions=True)

    async def configure(self, request: GenerationRequest) -> str | None:
        if request.optimization.mode != "standard":
            raise LatticeError(
                "Concurrent native worker requires standard execution",
                422,
                "concurrent_strategy_unqualified",
            )
        if (
            request.optimization.profile == "lowest_compute"
            or request.max_estimated_compute_ms is not None
        ):
            raise LatticeError(
                "Concurrent compute profiles are not qualified",
                422,
                "compute_model_unavailable",
            )
        if (
            request.max_memory_mb is not None
            and request.max_memory_mb < self._memory_cap
        ):
            raise LatticeError(
                "Request memory cap is below the shared worker ceiling; configure a smaller worker cap",
                422,
                "budget_infeasible",
            )
        return None

    def completion_payload(self, body: dict, execution_context=None) -> dict:
        lease = execution_context
        if lease is None:
            raise RuntimeError("Missing slot lease")
        lease.submitted = True
        lease.pid = self.process.pid
        return {**body, "id_slot": lease.slot, "cache_prompt": False}

    def completion_headers(self, execution_context=None) -> dict:
        lease = execution_context
        if lease is None:
            raise RuntimeError("Missing stream identity")
        return {"X-Conversation-Id": lease.conversation}

    def completion_response(self, execution_context=None) -> None:
        lease = execution_context
        if lease:
            lease.acknowledged = True

    async def abort_generation(self) -> None:
        # The enclosing lease finalizer explicitly cancels this native stream only.
        # Killing a shared worker here would interrupt unrelated requests.
        return

    def _release(self, lease: SlotLease) -> None:
        if lease.released:
            return
        lease.released = True
        self._quarantined.discard(lease)
        self._leases.pop(lease.slot, None)
        self._available.put_nowait(lease.slot)

    def _retire_if_idle(self) -> None:
        if self._quarantined and not self._live:
            self._retirements += 1
            self.stop()

    async def _finish(self, lease: SlotLease) -> None:
        if not lease.submitted:
            self._release(lease)
            return
        witnessed = lease.acknowledged
        deadline = time.monotonic() + 5.0
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.headers,
                timeout=1.0,
                trust_env=False,
            ) as client:
                while time.monotonic() < deadline:
                    if (
                        not self.process
                        or self.process.pid != lease.pid
                        or self.process.poll() is not None
                    ):
                        self._release(lease)
                        return
                    lookup = await client.post(
                        "/v1/streams/lookup",
                        json={"conversation_ids": [lease.conversation]},
                    )
                    lookup.raise_for_status()
                    witnessed = witnessed or any(
                        row["conversation_id"] == lease.conversation
                        for row in lookup.json()
                    )
                    if witnessed:
                        reply = await client.delete(
                            "/v1/stream", params={"conv_id": lease.conversation}
                        )
                        if reply.status_code != 204:
                            raise httpx.HTTPError(
                                "Native stream cancellation was not acknowledged"
                            )
                        slots = await client.get("/slots")
                        slots.raise_for_status()
                        own = next(
                            (row for row in slots.json() if row["id"] == lease.slot),
                            None,
                        )
                        if own is not None and not own["is_processing"]:
                            if not lease.completed:
                                self._verified_cancellations += 1
                            self._release(lease)
                            return
                    await asyncio.sleep(0.02)
        except (httpx.HTTPError, ValueError, KeyError):
            pass
        # Unknown native ownership is never returned to the free list. Restart only
        # after every live user stream has drained, preserving unrelated requests.
        self._unconfirmed_cancellations += 1
        self._quarantined.add(lease)
        self._retire_if_idle()

    async def events(self, request: GenerationRequest) -> AsyncIterator[dict]:
        fallback = None
        if request.optimization.mode != "standard":
            if not request.optimization.allow_fallback:
                raise LatticeError(
                    "Concurrent optimized paths lack quality evidence",
                    422,
                    "concurrent_strategy_unqualified",
                )
            fallback = "Concurrent batching uses standard execution; serial optimization evidence does not apply"
            request = request.model_copy(deep=True)
            request.optimization.mode = "standard"
        slot = await self._available.get()
        lease = SlotLease(slot, "lattice-" + uuid.uuid4().hex)
        self._leases[slot] = lease
        self._live.add(lease)
        try:
            async with contextlib.aclosing(
                super().events(request, execution_context=lease)
            ) as stream:
                async for event in stream:
                    if event["type"] == "prefill":
                        event = {
                            **event,
                            "native_slot": slot,
                            "native_slots": self.native_slots,
                            "fallback_reason": fallback,
                        }
                    elif event["type"] == "backend_done":
                        lease.completed = True
                    yield event
        finally:
            self._live.discard(lease)
            task = asyncio.create_task(self._finish(lease))
            self._cleanup_tasks.add(task)
            task.add_done_callback(self._cleanup_tasks.discard)
            try:
                await asyncio.shield(task)
            finally:
                self._retire_if_idle()

    def slot_stats(self) -> dict:
        return {
            "capacity": self.native_slots,
            "free": self._available.qsize(),
            "leased": len(self._leases),
            "quarantined": len(self._quarantined),
            "cleanup_tasks": len(self._cleanup_tasks),
            "verified_cancellations": self._verified_cancellations,
            "unconfirmed_cleanup": self._unconfirmed_cancellations,
            "drained_worker_retirements": self._retirements,
        }

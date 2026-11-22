"""Preemptive or non-preemptive priority admission with aging and cancellation-safe handoff."""

import asyncio
import time
from dataclasses import dataclass


@dataclass(eq=False)
class Waiter:
    priority: int
    sequence: int
    arrived: float
    future: asyncio.Future
    granted: bool = False
    estimated_work: int = 0


@dataclass(eq=False)
class Permit:
    sequence: int
    priority: int
    arrived: float
    preempt_event: asyncio.Event
    estimated_work: int = 0
    preempted: bool = False

    def __bool__(self) -> bool:
        return True

    @property
    def is_preempted(self) -> bool:
        return self.preempt_event.is_set()


class FairSemaphore:
    def __init__(
        self,
        capacity: int = 1,
        aging_seconds: float = 5.0,
        *,
        cost_aware: bool = False,
        preemptive: bool = False,
    ):
        if capacity < 1:
            raise ValueError("Admission capacity must be positive")
        self.capacity = capacity
        self.cost_aware = cost_aware
        self.preemptive = preemptive
        if aging_seconds <= 0:
            raise ValueError("Aging interval must be positive")
        self.aging_seconds = aging_seconds
        self._holders: list[Permit] = []
        self._waiters: list[Waiter] = []
        self._sequence = 0

    @property
    def active(self) -> int:
        return len(self._holders)

    def locked(self) -> bool:
        return len(self._holders) >= self.capacity

    def _check_preemption(self, incoming_priority: int) -> None:
        if not self.preemptive:
            return
        unpreempted = [
            h
            for h in self._holders
            if not h.preempted and h.priority < incoming_priority
        ]
        if not unpreempted:
            return
        # Pick the lowest priority holder (earliest sequence as tiebreaker)
        candidate = min(unpreempted, key=lambda h: (h.priority, h.sequence))
        candidate.preempted = True
        candidate.preempt_event.set()

    async def acquire(self, priority: int = 0, estimated_work: int = 0) -> Permit:
        if type(estimated_work) is not int or estimated_work < 0:
            raise ValueError("Estimated work must be a nonnegative integer proxy")
        if not self.locked():
            self._sequence += 1
            permit = Permit(
                sequence=self._sequence,
                priority=priority,
                arrived=time.monotonic(),
                preempt_event=asyncio.Event(),
                estimated_work=estimated_work,
            )
            self._holders.append(permit)
            return permit

        self._sequence += 1
        waiter = Waiter(
            priority,
            self._sequence,
            time.monotonic(),
            asyncio.get_running_loop().create_future(),
        )
        waiter.estimated_work = estimated_work
        self._waiters.append(waiter)

        if self.preemptive:
            self._check_preemption(priority)

        try:
            permit = await waiter.future
            return permit
        except BaseException:
            if waiter in self._waiters:
                self._waiters.remove(waiter)
            elif waiter.granted:
                self.release()  # cancellation after ownership was handed off
            raise

    def release(self, permit: Permit | None = None) -> None:
        if not self._holders:
            raise RuntimeError("Release without ownership")
        if permit is not None and permit in self._holders:
            self._holders.remove(permit)
        else:
            self._holders.pop(0)

        self._waiters = [w for w in self._waiters if not w.future.done()]
        if not self._waiters:
            return

        now = time.monotonic()
        chosen = max(
            self._waiters,
            key=lambda w: (
                w.priority + int((now - w.arrived) / self.aging_seconds),
                -w.estimated_work if self.cost_aware else 0,
                -w.sequence,
            ),
        )
        self._waiters.remove(chosen)
        chosen.granted = True

        new_permit = Permit(
            sequence=chosen.sequence,
            priority=chosen.priority,
            arrived=now,
            preempt_event=asyncio.Event(),
            estimated_work=chosen.estimated_work,
        )
        self._holders.append(new_permit)
        chosen.future.set_result(new_permit)


class FairLock(FairSemaphore):
    """Backwards-compatible single-permit admission."""

    def __init__(self, aging_seconds: float = 5.0, *, preemptive: bool = False):
        super().__init__(capacity=1, aging_seconds=aging_seconds, preemptive=preemptive)

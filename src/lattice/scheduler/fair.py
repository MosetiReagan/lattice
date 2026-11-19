"""Non-preemptive priority admission with aging and cancellation-safe handoff.

Native iteration batching remains a backend concern. This queue cannot preempt
an active generation and makes no claim of continuous batching.
"""

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


class FairSemaphore:
    def __init__(self, capacity: int = 1, aging_seconds: float = 5.0):
        if capacity < 1:
            raise ValueError("Admission capacity must be positive")
        self.capacity = capacity
        if aging_seconds <= 0:
            raise ValueError("Aging interval must be positive")
        self.aging_seconds = aging_seconds
        self._active = 0
        self._waiters = []
        self._sequence = 0

    @property
    def active(self) -> int:
        return self._active

    def locked(self) -> bool:
        return self._active >= self.capacity

    async def acquire(self, priority: int = 0) -> bool:
        if not self.locked():
            self._active += 1
            return True
        self._sequence += 1
        waiter = Waiter(
            priority,
            self._sequence,
            time.monotonic(),
            asyncio.get_running_loop().create_future(),
        )
        self._waiters.append(waiter)
        try:
            await waiter.future
            return True
        except BaseException:
            if waiter in self._waiters:
                self._waiters.remove(waiter)
            elif waiter.granted:
                self.release()  # cancellation after ownership was handed off
            raise

    def release(self):
        if not self._active:
            raise RuntimeError("Release without ownership")
        self._waiters = [w for w in self._waiters if not w.future.done()]
        if not self._waiters:
            self._active -= 1
            return
        now = time.monotonic()
        chosen = max(
            self._waiters,
            key=lambda w: (
                w.priority + int((now - w.arrived) / self.aging_seconds),
                -w.sequence,
            ),
        )
        self._waiters.remove(chosen)
        chosen.granted = True
        chosen.future.set_result(True)


class FairLock(FairSemaphore):
    """Backwards-compatible single-permit admission."""

    def __init__(self, aging_seconds: float = 5.0):
        super().__init__(capacity=1, aging_seconds=aging_seconds)

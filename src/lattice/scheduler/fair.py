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


class FairLock:
    def __init__(self, aging_seconds: float = 5.0):
        if aging_seconds <= 0:
            raise ValueError("Aging interval must be positive")
        self.aging_seconds = aging_seconds
        self._busy = False
        self._waiters = []
        self._sequence = 0

    def locked(self) -> bool:
        return self._busy

    async def acquire(self, priority: int = 0) -> bool:
        if not self._busy:
            self._busy = True
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
        if not self._busy:
            raise RuntimeError("Release without ownership")
        self._waiters = [w for w in self._waiters if not w.future.done()]
        if not self._waiters:
            self._busy = False
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

import asyncio
from unittest.mock import patch

import pytest

from lattice.scheduler.fair import FairLock


async def test_priority_fifo_and_cancelled_waiter():
    lock = FairLock()
    await lock.acquire()
    order = []

    async def waiting(name, priority):
        await lock.acquire(priority)
        order.append(name)
        lock.release()

    low = asyncio.create_task(waiting("low", 0))
    high = asyncio.create_task(waiting("high", 3))
    cancelled = asyncio.create_task(waiting("cancelled", 3))
    same = asyncio.create_task(waiting("same", 3))
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    lock.release()
    await asyncio.gather(low, high, same)
    assert order == ["high", "same", "low"] and not lock.locked()


async def test_aging_prevents_permanent_priority_starvation():
    lock = FairLock(1)
    await lock.acquire()
    order = []

    async def waiting(name, priority):
        await lock.acquire(priority)
        order.append(name)
        lock.release()

    with patch("lattice.scheduler.fair.time.monotonic", return_value=0):
        old = asyncio.create_task(waiting("old", 0))
        await asyncio.sleep(0)
    with patch("lattice.scheduler.fair.time.monotonic", return_value=10):
        new = asyncio.create_task(waiting("new", 3))
        await asyncio.sleep(0)
        lock.release()
        await asyncio.gather(old, new)
    assert order == ["old", "new"]


async def test_cancel_during_handoff_does_not_leak_lock():
    lock = FairLock()
    await lock.acquire()
    waiter = asyncio.create_task(lock.acquire())
    await asyncio.sleep(0)
    lock.release()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert not lock.locked()


async def test_cancelled_future_removed_before_task_cleanup_cannot_release_new_owner():
    lock = FairLock()
    await lock.acquire()
    cancelled = asyncio.create_task(lock.acquire())
    next_owner = asyncio.create_task(lock.acquire())
    await asyncio.sleep(0)
    cancelled.cancel()
    # release runs before cancelled acquire() gets its exception handler turn.
    lock.release()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    await next_owner
    assert lock.locked()
    third = asyncio.create_task(lock.acquire())
    await asyncio.sleep(0)
    assert not third.done()
    lock.release()
    await third
    assert lock.locked()
    lock.release()
    assert not lock.locked()


async def test_semaphore_bounds_concurrency_and_waiter_cancellation():
    from lattice.scheduler.fair import FairSemaphore

    admission = FairSemaphore(2)
    active = 0
    maximum = 0

    async def work(index):
        nonlocal active, maximum
        acquired = False
        try:
            await admission.acquire(index % 4)
            acquired = True
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.001)
        finally:
            if acquired:
                active -= 1
                admission.release()

    tasks = [asyncio.create_task(work(i)) for i in range(100)]
    await asyncio.sleep(0)
    for task in tasks[3::7]:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    assert maximum == 2 and active == 0 and admission.active == 0

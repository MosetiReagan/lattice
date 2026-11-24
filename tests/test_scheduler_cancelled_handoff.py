import asyncio

import pytest

from lattice.scheduler.fair import FairSemaphore


async def test_cancelled_handoff_retains_the_other_live_owner():
    semaphore = FairSemaphore(capacity=2, preemptive=True)
    first = await semaphore.acquire(priority=0)
    second = await semaphore.acquire(priority=1)
    cancelled = asyncio.create_task(semaphore.acquire(priority=3))
    await asyncio.sleep(0)
    semaphore.release(second)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    assert semaphore.active == 1
    assert semaphore._holders == [first], (
        "Cancellation removed the live peer instead of its own granted permit"
    )
    semaphore.release(first)
    assert semaphore.active == 0

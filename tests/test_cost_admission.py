import asyncio
from unittest.mock import patch

import pytest

from lattice.scheduler.fair import FairSemaphore


async def order_for(policy=True, priorities=(0, 0), costs=(1000, 10)):
    queue = FairSemaphore(1, cost_aware=policy)
    await queue.acquire()
    order = []

    async def submit(index):
        await queue.acquire(priorities[index], costs[index])
        order.append(index)
        queue.release()

    tasks = [asyncio.create_task(submit(i)) for i in range(2)]
    await asyncio.sleep(0)
    queue.release()
    await asyncio.gather(*tasks)
    return order


async def test_cost_tiebreak_is_opt_in():
    assert await order_for() == [1, 0]
    assert await order_for(False) == [0, 1]


async def test_explicit_priority_wins_over_cost():
    assert await order_for(priorities=(3, 0)) == [0, 1]


async def test_equal_cost_retains_fifo():
    assert await order_for(costs=(10, 10)) == [0, 1]


async def test_aging_outranks_cheap_newcomer():
    queue = FairSemaphore(1, aging_seconds=1, cost_aware=True)
    await queue.acquire()
    order = []

    async def submit(i, cost):
        await queue.acquire(0, cost)
        order.append(i)
        queue.release()

    with patch("lattice.scheduler.fair.time.monotonic", return_value=0):
        old = asyncio.create_task(submit(0, 10000))
        await asyncio.sleep(0)
    with patch("lattice.scheduler.fair.time.monotonic", return_value=2):
        new = asyncio.create_task(submit(1, 1))
        await asyncio.sleep(0)
        queue.release()
        await asyncio.gather(old, new)
    assert order == [0, 1]


async def test_cancelled_cost_waiter_does_not_leak_capacity():
    queue = FairSemaphore(1, cost_aware=True)
    await queue.acquire()
    task = asyncio.create_task(queue.acquire(0, 1))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    queue.release()
    assert not queue.locked()


@pytest.mark.parametrize("value", [-1, float("nan"), 1.0, True])
async def test_invalid_cost_proxy(value):
    with pytest.raises(ValueError):
        await FairSemaphore(1, cost_aware=True).acquire(0, value)

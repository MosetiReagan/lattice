"""Control-plane faults: no native/GPU execution is represented by these mocks."""

from types import SimpleNamespace

import httpx
import pytest

from lattice.backends.batched import BatchedLlamaBackend, SlotLease
from lattice.runtime import Runtime
from lattice.types import GenerationRequest, LatticeError


class NoSignalBackend(BatchedLlamaBackend):
    """Never sends OS signals; suitable for simulated process metadata only."""

    def stop(self):
        self.stopped = True
        self.process = None
        for lease in list(self._quarantined):
            self._release(lease)


@pytest.fixture
def backend(settings):
    settings.native_slots = 2
    settings.models[0].kv_bytes_per_token = 12288
    result = NoSignalBackend(settings, settings.models[0])
    result.stopped = False
    return result


def test_parallel_model_swap_is_rejected(settings, backend):
    with pytest.raises(ValueError, match="pins one model"):
        Runtime(settings, "test-model", backend, backend_factory=lambda model: backend)


async def test_uncertain_cleanup_quarantines_instead_of_recycling_or_killing_peer(
    backend, monkeypatch
):
    one = SlotLease(
        await backend._available.get(), "one", pid=77, submitted=True, acknowledged=True
    )
    peer = SlotLease(await backend._available.get(), "peer")
    backend._leases = {one.slot: one, peer.slot: peer}
    backend._live.add(peer)
    backend.process = SimpleNamespace(pid=77, poll=lambda: None)
    backend.base_url = "http://private-native"
    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    monkeypatch.setattr(
        "lattice.backends.batched.httpx.AsyncClient",
        lambda **kwargs: original(**kwargs, transport=transport),
    )
    await backend._finish(one)
    assert not backend.stopped and backend.slot_stats()["quarantined"] == 1
    assert backend.slot_stats()["free"] == 0
    assert backend.slot_stats()["draining"]
    backend._live.clear()
    backend._release(peer)
    backend._retire_if_idle()
    assert backend.stopped and backend.slot_stats()["free"] == 2
    assert not backend.slot_stats()["draining"]


async def test_concurrent_constraints_never_mutate_shared_worker(backend):
    initial = backend._memory_cap
    with pytest.raises(LatticeError):
        await backend.configure(
            GenerationRequest(model="test-model", prompt="x", max_memory_mb=1024)
        )
    assert backend._memory_cap == initial and not backend.stopped
